// 在用户的工作区里运行某个技能的 Python 脚本。
//
// 参数按数组直接交给 Python，不经过 PowerShell / bash：中文路径、空格、引号都不用转义，也不会被 shell 改写。
// 只允许运行随插件附带的技能目录里的 .py 文件；工作目录必须在会话工作区之内。

import { spawn } from 'node:child_process'
import { existsSync, readdirSync, realpathSync, statSync } from 'node:fs'
import { delimiter, isAbsolute, join, relative, resolve, sep } from 'node:path'

export const MAX_OUTPUT = 24000          // 交给模型的 stdout / stderr 各保留末尾这么多字符
const MAX_CAPTURE = 4 * 1024 * 1024      // 内存里最多留这么多字节，防止失控输出撑爆
const SCAN_SKIP = new Set(['node_modules', '.git', '__pycache__', '.dsh', '.venv', 'venv'])

function real(p) {
  try { return realpathSync(p) } catch { return resolve(p) }
}

/** child 是否位于 parent 之内（含相等）。两边都先解析符号链接。 */
export function isInside(child, parent) {
  const rel = relative(real(parent), real(child))
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}

/**
 * 把模型给的 script 解析成绝对路径。接受「相对技能目录」（scripts/make.py）或指向技能目录内的绝对路径
 * （脚本自己打印的下一步命令常写成绝对路径）。不在技能目录里、不是 .py、不存在，一律拒绝并说明。
 */
export function resolveScript(skillsRoot, skill, script) {
  const skillDir = join(skillsRoot, skill)
  if (!existsSync(join(skillDir, 'SKILL.md'))) throw new Error(`没有这个技能：${skill}`)
  const s = String(script || '').trim().replace(/^["']|["']$/g, '')
  if (!s) throw new Error('script 不能为空，例如 scripts/make.py')
  let abs = isAbsolute(s) ? s : join(skillDir, s)
  if (!isAbsolute(s) && !existsSync(abs)) {
    // 模型有时会把技能名带进来：mqc-legal-chart-master/scripts/make.py
    const alt = join(skillsRoot, s)
    if (existsSync(alt)) abs = alt
  }
  if (!abs.toLowerCase().endsWith('.py')) throw new Error(`只能运行 .py 脚本，收到：${s}`)
  if (!existsSync(abs) || !statSync(abs).isFile()) throw new Error(`找不到脚本：${s}（相对技能目录 ${skill} 来写，例如 scripts/make.py）`)
  if (!isInside(abs, skillsRoot)) throw new Error(`只能运行随插件附带的技能脚本，这个路径在技能目录之外：${s}`)
  return real(abs)
}

/** 工作目录：会话工作区，或其中的子目录。 */
export function resolveWorkdir(sessionCwd, workdir) {
  const base = real(sessionCwd)
  if (!workdir) return base
  const abs = isAbsolute(workdir) ? workdir : join(base, workdir)
  if (!existsSync(abs) || !statSync(abs).isDirectory()) throw new Error(`工作目录不存在：${workdir}`)
  if (!isInside(abs, base)) throw new Error(`工作目录必须在当前会话的工作区之内：${workdir}`)
  return real(abs)
}

/**
 * 参数里写成「相对技能目录」的输入文件（例如示例 examples/a.json）：工作区里没有、技能目录里有，就换成完整路径。
 * 只换「看起来是相对路径、且在技能目录里确实存在的文件或文件夹」，输出路径（事先不存在）与选项不受影响。
 */
export function resolveSkillFileArgs(args, cwd, skillDir) {
  const resolved = []
  const argv = args.map((a) => {
    const s = String(a)
    if (!s || s.startsWith('-') || isAbsolute(s) || s.includes('\u0000')) return s
    if (existsSync(join(cwd, s))) return s
    const cand = join(skillDir, s)
    if (existsSync(cand) && isInside(cand, skillDir)) {
      resolved.push({ from: s, to: cand })
      return cand
    }
    return s
  })
  return { argv, resolved }
}

/** 本次运行期间新写出或改动过的文件（工作区内，浅层扫描，最多 limit 个）。 */
export function changedFiles(root, sinceMs, { depth = 5, limit = 60, maxEntries = 20000 } = {}) {
  const found = []
  let seen = 0
  const walk = (dir, d) => {
    if (d > depth || found.length >= limit || seen > maxEntries) return
    let names
    try { names = readdirSync(dir, { withFileTypes: true }) } catch { return }
    for (const e of names) {
      if (found.length >= limit || ++seen > maxEntries) return
      if (e.name.startsWith('.')) continue
      const p = join(dir, e.name)
      if (e.isDirectory()) {
        if (!SCAN_SKIP.has(e.name)) walk(p, d + 1)
      } else if (e.isFile()) {
        try { if (statSync(p).mtimeMs >= sinceMs) found.push(p) } catch { /* 刚被删 */ }
      }
    }
  }
  walk(root, 0)
  return found.sort()
}

function tail(s) {
  return s.length > MAX_OUTPUT ? '……（前面省略 ' + (s.length - MAX_OUTPUT) + ' 个字符）\n' + s.slice(-MAX_OUTPUT) : s
}

function killTree(child) {
  if (!child || child.exitCode !== null) return
  if (process.platform === 'win32') {
    try { spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true }) } catch { /* 忽略 */ }
  } else {
    try { process.kill(-child.pid, 'SIGTERM') } catch { try { child.kill('SIGTERM') } catch { /* 忽略 */ } }
  }
}

/**
 * 运行一次脚本。返回规范值（JSON），不抛出脚本自身的失败——非零退出照实写进结果，由模型读报错改输入。
 */
export function runScript({ python, scriptPath, args = [], cwd, timeoutSec = 600, signal, pythonPath = [], nodePath = [] }) {
  return new Promise((resolvePromise, reject) => {
    const started = Date.now()
    const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1', NLV_HOST: 'deepseek-harness' }
    const extra = pythonPath.filter((p) => existsSync(p))
    if (extra.length) env.PYTHONPATH = [...extra, ...(env.PYTHONPATH ? [env.PYTHONPATH] : [])].join(delimiter)
    // 脚本另起 node 写 Word 时（require('docx')），从随插件附带的 node_modules 找
    const nodeExtra = nodePath.filter((p) => existsSync(p))
    if (nodeExtra.length) env.NODE_PATH = [...nodeExtra, ...(env.NODE_PATH ? [env.NODE_PATH] : [])].join(delimiter)
    let child
    try {
      child = spawn(python.cmd, [...python.pre, scriptPath, ...args.map(String)], {
        cwd, env, windowsHide: true, detached: process.platform !== 'win32',
      })
    } catch (e) {
      return reject(new Error(`启动 Python 失败：${e?.message || e}`))
    }
    let out = Buffer.alloc(0)
    let err = Buffer.alloc(0)
    const keep = (buf, d) => {
      const b = Buffer.concat([buf, d])
      return b.length > MAX_CAPTURE ? b.subarray(b.length - MAX_CAPTURE) : b
    }
    child.stdout.on('data', (d) => { out = keep(out, d) })
    child.stderr.on('data', (d) => { err = keep(err, d) })
    let timedOut = false
    let aborted = false
    const timer = setTimeout(() => { timedOut = true; killTree(child) }, Math.max(5, timeoutSec) * 1000)
    const onAbort = () => { aborted = true; killTree(child) }
    if (signal) {
      if (signal.aborted) onAbort()
      else signal.addEventListener('abort', onAbort, { once: true })
    }
    let settled = false
    const settle = (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal?.removeEventListener?.('abort', onAbort)
      if (aborted) return reject(Object.assign(new Error('已取消'), { name: 'AbortError' }))
      const files = changedFiles(cwd, started - 1000)
      resolvePromise({
        exitCode: timedOut ? null : code,
        timedOut,
        durationMs: Date.now() - started,
        cwd,
        script: scriptPath,
        stdout: tail(out.toString('utf8')),
        stderr: tail(err.toString('utf8')),
        files,
      })
    }
    child.on('error', (e) => { clearTimeout(timer); if (!settled) { settled = true; reject(new Error(`运行失败：${e.message}`)) } })
    // 用 exit 而不是 close：脚本若另起了常驻进程（例如课件编辑器的 --detach），close 会一直等到那个进程退出
    child.on('exit', (code) => setTimeout(() => settle(code), 150))
    child.on('close', (code) => settle(code))
  })
}
