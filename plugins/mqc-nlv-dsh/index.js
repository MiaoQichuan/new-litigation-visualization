// 新诉讼可视化 · DeepSeek Harness 插件：原生工具。
//
//   nlv_check  查本机环境：Python 在不在、版本够不够、可选工具有哪些，缺了怎么装
//   nlv_run    在用户的工作区里运行某个技能的 Python 脚本（参数直传，不经 shell）
//
// 七个技能本身由同包的 ./skill-provider.js 注册。出图、核验、守卫都在各技能的 Python 脚本里，
// 这里只负责找到 Python、把脚本安全地跑起来、把新写出的文件列给模型，好让它用 present 交付。
//
// Copyright (C) 2026 缪奇川（Miao Qichuan）. AGPL-3.0-only.

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineTool } from '@deepseek-ai/dsh-tools'

import { findPython, installHelp, MIN_PYTHON } from './lib/python.js'
import { resolveScript, resolveSkillFileArgs, resolveWorkdir, runScript } from './lib/run.js'
import { findSoffice, readJson, shadowingCopies, which } from './lib/env.js'

export const name = 'mqc-nlv-dsh'
export const inject = ['tools']

const ROOT = dirname(fileURLToPath(import.meta.url))
const SKILLS_ROOT = join(ROOT, 'nlv-skills')
const PY_VENDOR = join(ROOT, 'python')
const NODE_VENDOR = join(ROOT, 'nodejs', 'node_modules')
const MANIFEST = readJson(join(SKILLS_ROOT, 'skills.json'), { skills: [] })
const SKILL_NAMES = MANIFEST.skills.map((s) => s.name)
const VERSION = readJson(join(ROOT, 'package.json'), {}).version || ''

/** 当前会话的工作目录：优先读工作目录服务（会随 cd 变化），其次是会话创建时的目录。 */
function sessionCwd(ctx, exec) {
  const session = exec?.agent?.session
  try {
    const wd = ctx.get?.('workingDirectory')
    if (wd && session) return wd.get(session)
  } catch { /* 服务不在，退回 header */ }
  return session?.header?.cwd || process.cwd()
}

/** 用找到的 Python 跑一行代码，判断某个包能不能 import（带上随插件附带的 openpyxl）。 */
function canImport(python, mod) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(python.cmd, [...python.pre, '-c', `import ${mod}`], {
        windowsHide: true,
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: [PY_VENDOR, process.env.PYTHONPATH].filter(Boolean).join(process.platform === 'win32' ? ';' : ':') },
      })
    } catch { return resolve(false) }
    const t = setTimeout(() => { try { child.kill() } catch { /* 忽略 */ } resolve(false) }, 20000)
    child.on('error', () => { clearTimeout(t); resolve(false) })
    child.on('close', (code) => { clearTimeout(t); resolve(code === 0) })
  })
}

function textBlock(text) {
  return [{ type: 'text', text }]
}

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'nlv_check',
    description:
      '新诉讼可视化：检查本机能不能运行七个诉讼可视化技能（Python 是否可用、版本、Excel / PNG / Word 等可选能力）。'
      + '第一次使用新诉讼可视化、或 nlv_run 报告找不到 Python 时调用；把返回的安装说明原样转告用户。',
    parameters: {
      refresh: { type: 'boolean', description: '重新查找 Python（用户刚装好 Python 时传 true）。' },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, v) => textBlock(renderCheck(v)),
    },
    async execute(args, exec) {
      const py = await findPython({ refresh: args.refresh === true })
      const cwd = sessionCwd(ctx, exec)
      const shadow = shadowingCopies(SKILL_NAMES, cwd)
      const result = {
        plugin: VERSION,
        skills: SKILL_NAMES,
        python: py.ok ? { ok: true, version: py.version, command: [py.cmd, ...py.pre].join(' '), executable: py.executable } : { ok: false },
        tried: py.ok ? [] : py.tried,
        help: py.ok ? '' : installHelp(),
        optional: {},
        shadowed: shadow,
      }
      if (py.ok) {
        result.optional.excel = (await canImport(py, 'openpyxl')) ? '可用（openpyxl 随插件附带）' : '不可用：openpyxl 读不进来'
        result.optional.pillow = (await canImport(py, 'PIL')) ? '可用' : '未装（只影响庭审对抗图的 PNG 预览，可 pip install pillow numpy）'
      }
      const soffice = findSoffice()
      result.optional.libreoffice = soffice ? `可用：${soffice}` : '未装（PNG 预览、读 PPT 模板缩略图会跳过；SVG、PPTX、Excel 不受影响）'
      result.optional.graphviz = which('dot') ? '可用' : '未装（可选：V1 流程图有自带排版，不装也能出）'
      const hasNode = which('node')
      const hasDocx = existsSync(join(NODE_VENDOR, 'docx', 'dist', 'index.cjs'))
      result.optional.word = hasNode && hasDocx ? '可用（Node.js 已装，docx 随插件附带）'
        : hasNode ? '不可用：插件包里缺 docx（请重装插件）'
          : '未装 Node.js（可选：只影响时间轴的 Word 溯源索引、大事记的 Word 版；没有时大事记改出同内容的 Markdown 版。要 Word 就到 https://nodejs.org 下载 LTS 版安装，装好后重启 DeepSeek Harness）'
      return result
    },
  }))

  ctx.tools.register(defineTool({
    name: 'nlv_run',
    description:
      '新诉讼可视化：在用户的工作区里运行某个技能的 Python 脚本。技能说明里写成 `python3 <本技能目录>/scripts/x.py 参数…` 的命令，'
      + '一律改用本工具：skill 填技能名，script 填相对技能目录的路径（如 scripts/x.py），args 按顺序逐项填参数（不要自己加引号）。'
      + '不要在终端里直接敲 python3 / python。结果里的 files 是本次新写出的文件；成品请再用 present 交付给用户。',
    parameters: {
      skill: { type: 'string', required: true, ...(SKILL_NAMES.length ? { enum: SKILL_NAMES } : {}), description: '技能名，例如 mqc-legal-chart-master。' },
      script: { type: 'string', required: true, description: '相对技能目录的脚本路径，例如 scripts/make.py。' },
      args: { type: 'array', items: { type: 'string' }, description: '传给脚本的参数，按顺序每项一个，例如 ["examples/a.json", "-o", "图/a"]。路径写相对工作区的路径。' },
      workdir: { type: 'string', description: '在工作区里的哪个子目录运行；不写就是工作区本身。' },
      timeoutSec: { type: 'integer', description: '最长运行秒数，默认 600，最多 1800。' },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, v) => textBlock(renderRun(v)),
    },
    async execute(args, exec) {
      const py = await findPython()
      if (!py.ok) {
        return { ok: false, reason: 'no-python', help: installHelp(), tried: py.tried }
      }
      const scriptPath = resolveScript(SKILLS_ROOT, args.skill, args.script)
      const cwd = resolveWorkdir(sessionCwd(ctx, exec), args.workdir)
      const timeoutSec = Math.min(1800, Math.max(5, args.timeoutSec ?? 600))
      const { argv, resolved } = resolveSkillFileArgs(args.args ?? [], cwd, join(SKILLS_ROOT, args.skill))
      const r = await runScript({
        python: py, scriptPath, args: argv, cwd, timeoutSec, signal: exec?.signal, pythonPath: [PY_VENDOR], nodePath: [NODE_VENDOR],
      })
      return { ok: r.exitCode === 0, skill: args.skill, python: py.version, ...(resolved.length ? { resolvedArgs: resolved } : {}), ...r }
    },
  }))
}

function renderCheck(v) {
  const lines = [`新诉讼可视化 ${v.plugin} · 环境自检`]
  if (v.python?.ok) {
    lines.push(`Python：可用 ${v.python.version}（${v.python.command}）`)
  } else {
    lines.push(`Python：没有找到可用的 Python（需要 ${MIN_PYTHON.join('.')} 或更新）。请把下面的说明原样转告用户：`, '', v.help)
    if (v.tried?.length) lines.push('', '试过：' + v.tried.join('；'))
  }
  for (const [k, s] of Object.entries(v.optional || {})) lines.push(`${k}：${s}`)
  lines.push(`技能：${(v.skills || []).join('、')}`)
  if (v.shadowed?.length) {
    lines.push('', '注意：下面这些位置有以前手动装的同名技能，DeepSeek Harness 会优先用它们而不是插件里的版本；'
      + '旧版本里的命令写的是 python3，在 Windows 上会出错。请告诉用户把这些文件夹移走或删除，再新开一个会话：',
    ...v.shadowed.map((p) => '  ' + p))
  }
  return lines.join('\n')
}

function renderRun(v) {
  if (v.reason === 'no-python') {
    return '没有找到可用的 Python，脚本没有运行。请把下面的说明原样转告用户：\n\n' + v.help
  }
  const head = v.timedOut ? `超时未完成（${Math.round(v.durationMs / 1000)} 秒），已停止。`
    : `退出码 ${v.exitCode}（${v.exitCode === 0 ? '成功' : '失败：读 stderr 里的报错，按它说的改输入再跑'}），用时 ${(v.durationMs / 1000).toFixed(1)} 秒。`
  const parts = [head, `工作目录：${v.cwd}`]
  if (v.stdout?.trim()) parts.push('--- stdout ---', v.stdout.trimEnd())
  if (v.stderr?.trim()) parts.push('--- stderr ---', v.stderr.trimEnd())
  if (v.files?.length) {
    parts.push('--- 本次新写出或改动的文件 ---', ...v.files.map((f) => f))
    if (v.exitCode === 0) parts.push('成品（SVG、PPTX、XLSX、DOCX、PNG 等）请用 present 交付给用户；中间文件（.json 等）不必交付。')
  }
  return parts.join('\n')
}
