// 找本机的 Python，并说清没有时怎么装。
//
// 为什么不直接写 python3：DeepSeek Harness 在 Windows 上用 PowerShell 执行命令，那里没有 python3 这个名字；
// python.org 安装包默认不勾「Add to PATH」时，python 也找不到；Windows 自带的 python.exe 只是一个跳到
// 应用商店的占位程序，一运行就退出。所以这里逐个候选真的跑一次，读到版本号才算找到。
// macOS 上从「访达」启动的桌面应用，PATH 里常常没有 Homebrew 的目录，所以也查常见的绝对路径。

import { spawn } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

export const MIN_PYTHON = [3, 9]

const PROBE = 'import sys, json; print(json.dumps({"v": list(sys.version_info[:3]), "exe": sys.executable}))'

/** 本机上可能是 Python 的命令，按先后顺序。每一项是 [程序, 前置参数]。 */
export function candidates(platform = process.platform, env = process.env) {
  // 用户（或管理员）用 NLV_PYTHON 指定了 Python，就只用它：指错了要明说，不悄悄换成别的
  if (env.NLV_PYTHON) return [[env.NLV_PYTHON, []]]
  const out = []
  if (platform === 'win32') {
    out.push(['py', ['-3']], ['python', []], ['python3', []])
    // python.org 安装包的默认位置（按用户安装、没勾 Add to PATH 时只在这里）
    for (const base of [env.LOCALAPPDATA && join(env.LOCALAPPDATA, 'Programs', 'Python'),
                        env.ProgramFiles, env['ProgramFiles(x86)']]) {
      if (!base || !existsSync(base)) continue
      let names = []
      try { names = readdirSync(base) } catch { names = [] }
      for (const n of names.filter((x) => /^Python3\d+/i.test(x)).sort().reverse()) {
        const exe = join(base, n, 'python.exe')
        if (existsSync(exe)) out.push([exe, []])
      }
    }
  } else {
    out.push(['python3', []], ['python', []])
    for (const p of ['/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3',
                     '/Library/Frameworks/Python.framework/Versions/Current/bin/python3']) {
      if (existsSync(p)) out.push([p, []])
    }
  }
  const seen = new Set()
  return out.filter(([cmd, pre]) => {
    const k = cmd + '\u0000' + pre.join(' ')
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

/** 跑一个候选，读出版本；不是 Python、版本太旧、超时都返回 null 与原因。 */
export function probe([cmd, pre], timeoutMs = 15000) {
  return new Promise((resolve) => {
    let out = ''
    let err = ''
    let done = false
    let child
    const finish = (value) => { if (!done) { done = true; clearTimeout(timer); resolve(value) } }
    try {
      child = spawn(cmd, [...pre, '-c', PROBE], { windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } })
    } catch (e) {
      return resolve({ ok: false, cmd, reason: String(e?.message || e) })
    }
    const timer = setTimeout(() => { try { child.kill() } catch { /* 已退出 */ } finish({ ok: false, cmd, reason: '超时' }) }, timeoutMs)
    child.stdout.on('data', (d) => { out += d })
    child.stderr.on('data', (d) => { err += d })
    child.on('error', (e) => finish({ ok: false, cmd, reason: e.code === 'ENOENT' ? '没有这个命令' : String(e.message || e) }))
    child.on('close', (code) => {
      const line = out.trim().split(/\r?\n/).pop() || ''
      try {
        const info = JSON.parse(line)
        const [major, minor] = info.v
        if (major < MIN_PYTHON[0] || (major === MIN_PYTHON[0] && minor < MIN_PYTHON[1])) {
          return finish({ ok: false, cmd, reason: `版本 ${info.v.join('.')} 太旧，需要 ${MIN_PYTHON.join('.')} 或更新` })
        }
        finish({ ok: true, cmd, pre, version: info.v.join('.'), executable: info.exe })
      } catch {
        finish({ ok: false, cmd, reason: `退出码 ${code}，不是可用的 Python${err.trim() ? '：' + err.trim().split(/\r?\n/).pop() : ''}` })
      }
    })
  })
}

let cached = null

/** 找到第一个可用的 Python；结果缓存到进程结束（装好 Python 后调 nlv_check 会重新找）。 */
export async function findPython({ refresh = false } = {}) {
  if (cached && !refresh) return cached
  const tried = []
  for (const c of candidates()) {
    const r = await probe(c)
    if (r.ok) {
      cached = { ...r, tried }
      return cached
    }
    tried.push(`${[c[0], ...c[1]].join(' ')}：${r.reason}`)
  }
  cached = null
  return { ok: false, tried }
}

/** 没找到 Python 时，给用户看的安装说明（照原样转告）。 */
export function installHelp(platform = process.platform) {
  const common = '装好之后**完全退出 DeepSeek Harness 再打开**（它启动时才读取新的 PATH），然后在对话里说「检查新诉讼可视化的环境」。'
  if (platform === 'win32') {
    return [
      '这台电脑还没有可用的 Python（需要 3.9 或更新的版本）。新诉讼可视化的出图引擎是 Python 写的，装一次即可：',
      '1. 打开 https://www.python.org/downloads/ ，下载 Windows 版安装包（选 3.12 或 3.13 均可）；',
      '2. 运行安装包，**第一页底部勾选「Add python.exe to PATH」**，再点「Install Now」；',
      '   也可以在 PowerShell 里运行：winget install Python.Python.3.12',
      '3. ' + common,
      '出 Excel 用的 openpyxl 已随插件附带，不需要另装。',
    ].join('\n')
  }
  if (platform === 'darwin') {
    return [
      '这台电脑还没有可用的 Python（需要 3.9 或更新的版本）。新诉讼可视化的出图引擎是 Python 写的，装一次即可：',
      '1. 打开 https://www.python.org/downloads/ ，下载 macOS 版安装包并安装；用 Homebrew 的也可以运行：brew install python',
      '2. ' + common,
      '出 Excel 用的 openpyxl 已随插件附带，不需要另装。',
    ].join('\n')
  }
  return [
    '这台电脑还没有可用的 Python（需要 3.9 或更新的版本）。请用系统的包管理器安装 python3（例如 sudo apt install python3），',
    common,
  ].join('\n')
}
