// 新诉讼可视化 · DeepSeek Harness 插件的回归：用模拟宿主把插件装起来，逐项核对。
//
//   node plugins/mqc-nlv-dsh/tests/dsh_checks.mjs
//
// 做的事：打包（build.py）→ 解压成 node_modules/mqc-nlv-dsh → 按 cordis.patch.yml 的两行加载插件 →
// 核对注册的工具与技能 → 用 nlv_run 真跑七个技能的示例 → 核对越权路径被拒、取消与超时、没有 Python 时的说法。
//
// defineTool：设了环境变量 DSH_SRC（DeepSeek Harness 源码目录）时用它的真实现（Node 自带的类型剥离直接读 .ts）；
// 没设时用本文件里按官方文档写的严格替身。真实现那一遍是发版前在本地跑的。

import { execFileSync, spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync, cpSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const PLUGIN = resolve(HERE, '..')
const PY = process.env.NLV_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
let fails = 0
let total = 0
function ok(label, cond, detail = '') {
  total += 1
  if (!cond) fails += 1
  console.log(`  ${cond ? 'OK  ' : 'FAIL'}  ${label}${!cond && detail ? '  → ' + String(detail).slice(0, 400) : ''}`)
}
function section(t) { console.log('\n　' + t) }

// ---------------------------------------------------------------- 打包、解压
const TMP = mkdtempSync(join(tmpdir(), 'nlv-dsh-'))
const DIST = join(TMP, 'dist')
section('打包')
execFileSync(PY, [join(PLUGIN, 'build.py'), '-o', DIST], { stdio: 'pipe' })
const pkgJson = JSON.parse(readFileSync(join(PLUGIN, 'package.json'), 'utf8'))
const TGZ = join(DIST, `${pkgJson.name}-${pkgJson.version}.tgz`)
ok('build.py 打出 tgz', existsSync(TGZ), TGZ)
const sha = (p) => createHash('sha256').update(readFileSync(p)).digest('hex')
const first = sha(TGZ)
execFileSync(PY, [join(PLUGIN, 'build.py'), '-o', DIST], { stdio: 'pipe' })
ok('同一份源码打两次，tgz 逐字节一致', sha(TGZ) === first)
ok('tgz 不超过 8 MB', statSync(TGZ).size < 8 * 1024 * 1024, statSync(TGZ).size)

const NM = join(TMP, 'host', 'node_modules')
mkdirSync(NM, { recursive: true })
execFileSync('tar', ['xzf', TGZ, '-C', TMP])
cpSync(join(TMP, 'package'), join(NM, 'mqc-nlv-dsh'), { recursive: true })
const PKG = join(NM, 'mqc-nlv-dsh')

// ---------------------------------------------------------------- 宿主替身
const DSH_SRC = process.env.DSH_SRC
const toolsDir = join(NM, '@deepseek-ai', 'dsh-tools')
mkdirSync(toolsDir, { recursive: true })
if (DSH_SRC) {
  // 真实现：源码复制到 node_modules 之外（Node 不剥离 node_modules 里的 .ts），它 import 的两个包从临时目录的 node_modules 解析
  const src = join(TMP, 'dshsrc')
  mkdirSync(join(src, 'util-values'), { recursive: true })
  cpSync(join(DSH_SRC, 'packages', 'util', 'values', 'src'), join(src, 'util-values', 'src'), { recursive: true })
  writeFileSync(join(src, 'util-values', 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-util-values', type: 'module', exports: { '.': './src/index.ts' } }))
  mkdirSync(join(src, 'tools'), { recursive: true })
  cpSync(join(DSH_SRC, 'packages', 'core', 'tools', 'src'), join(src, 'tools', 'src'), { recursive: true })
  writeFileSync(join(src, 'tools', 'package.json'), JSON.stringify({ type: 'module' }))
  writeFileSync(join(src, 'tools', 'entry.mjs'), "export { defineTool } from './src/schema.ts'\n")
  const llm = join(TMP, 'node_modules', '@deepseek-ai', 'dsh-llm')
  mkdirSync(llm, { recursive: true })
  writeFileSync(join(llm, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-llm', type: 'module', exports: { '.': './index.js' } }))
  writeFileSync(join(llm, 'index.js'), 'export class HarnessError extends Error { constructor(m, code, o) { super(m, o); this.code = code; this.name = new.target.name } }\n')
  mkdirSync(join(TMP, 'node_modules', '@deepseek-ai'), { recursive: true })
  symlinkSync(join(src, 'util-values'), join(TMP, 'node_modules', '@deepseek-ai', 'dsh-util-values'))
  writeFileSync(join(toolsDir, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', type: 'module', exports: { '.': './index.js' } }))
  writeFileSync(join(toolsDir, 'index.js'), `export { defineTool } from ${JSON.stringify(pathToFileURL(join(src, 'tools', 'entry.mjs')).href)}\n`)
} else {
  writeFileSync(join(toolsDir, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh-tools', type: 'module', exports: { '.': './index.js' } }))
  writeFileSync(join(toolsDir, 'index.js'), readFileSync(join(HERE, 'define_tool_stub.mjs'), 'utf8'))
}

const tools = new Map()
let provider = null
const ctx = {
  tools: { register(def) { if (tools.has(def.name)) throw new Error('重复注册 ' + def.name); tools.set(def.name, def) } },
  skills: { registerProvider(create) { provider = create({ signal: new AbortController().signal, invalidate() {} }) } },
  get() { return undefined },
}

section(`加载插件（defineTool：${DSH_SRC ? 'DeepSeek Harness 真实现' : '按文档写的严格替身'}）`)
const patch = readFileSync(join(PKG, 'cordis.patch.yml'), 'utf8')
const rows = [...patch.matchAll(/name:\s*['"]?([^'"\s]+)['"]?/g)].map((m) => m[1])
ok('cordis.patch.yml 插入两行：工具与技能', rows.length === 2 && rows[0] === 'mqc-nlv-dsh' && rows[1] === 'mqc-nlv-dsh/skill-provider', rows)
const loader = join(TMP, 'host', 'load.mjs')
writeFileSync(loader, 'export const load = (s) => import(s)\n')
const { load } = await import(pathToFileURL(loader).href)
const mods = []
for (const r of rows) {
  try { mods.push(await load(r)) } catch (e) { ok(`按包名载入 ${r}`, false, e.stack) }
}
ok('两行都按包名载入（exports 写对了）', mods.length === 2)
const [toolsMod, skillsMod] = mods
ok('工具插件：name、inject=[tools]、apply', toolsMod?.name && JSON.stringify(toolsMod.inject) === '["tools"]' && typeof toolsMod.apply === 'function')
ok('技能插件：name、inject=[skills]、apply', skillsMod?.name && JSON.stringify(skillsMod.inject) === '["skills"]' && typeof skillsMod.apply === 'function')
ok('两个插件名不同', toolsMod?.name !== skillsMod?.name)
try { toolsMod.apply(ctx) } catch (e) { ok('工具插件 apply 不抛错', false, e.stack) }
try { skillsMod.apply(ctx) } catch (e) { ok('技能插件 apply 不抛错', false, e.stack) }
ok('注册 nlv_check 与 nlv_run 两个工具', tools.has('nlv_check') && tools.has('nlv_run'), [...tools.keys()])
const runParams = tools.get('nlv_run')?.parameters
ok('nlv_run 的参数表：skill 与 script 必填，skill 只能取七个技能名', runParams?.required?.includes('skill') && runParams?.required?.includes('script')
  && runParams?.properties?.skill?.enum?.length === 7, JSON.stringify(runParams))

// ---------------------------------------------------------------- 技能
section('七个技能')
const list = await provider.list()
ok('列出七个技能', list.length === 7, list.map((x) => x.name))
const NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
ok('技能名都是小写连字符，描述不空，provider 与提供者同名', list.every((c) => NAME.test(c.name) && c.description.length > 0 && c.provider === provider.name))
ok('每个技能的目录与 SKILL.md 都在包里', list.every((c) => c.resourceBase.kind === 'directory' && existsSync(join(c.resourceBase.path, 'SKILL.md')) && existsSync(c.path)))
ok('排序值是随包技能的标准值 600，调用策略模型与用户都可', list.every((c) => c.rank === 600 && c.invocation.modelInvocable && c.invocation.userInvocable))
for (const c of list) {
  const d = await provider.get(c)
  const body = d.content
  const good = d.name === c.name && body.startsWith('## 在 DeepSeek Harness 里怎么运行本技能') && body.includes('`' + c.name + '`')
    && !/^---\s*\nname:/m.test(body) && !body.includes('{{skill}}') && body.includes('nlv_run') && body.length > 2000
  ok(`${c.name}：正文 = DSH 前言（填好技能名）+ 去掉 YAML 头的 SKILL.md`, good, body.slice(0, 200))
}
const longDesc = list.find((c) => c.name === 'mqc-timeline-master')?.description || ''
ok('折叠写法（>-）的描述读成一整段', longDesc.startsWith('Turn raw case materials') && !longDesc.includes('\n') && longDesc.length > 300, longDesc.slice(0, 80))

// ---------------------------------------------------------------- 工具：环境自检
section('nlv_check')
const WS = join(TMP, '工作区 一')
mkdirSync(WS, { recursive: true })
const exec = (cwd = WS, signal = new AbortController().signal) => ({ agent: { session: { header: { cwd } } }, signal })
const check = await tools.get('nlv_check').execute({}, exec())
ok('找到 Python', check.python?.ok, JSON.stringify(check))
ok('Excel 可用（openpyxl 随插件附带）', String(check.optional?.excel).startsWith('可用'), check.optional?.excel)
const checkText = tools.get('nlv_check').output.render({}, check).map((b) => b.text).join('')
ok('Word：本机有 Node.js 时报可用（docx 随插件附带）', String(check.optional?.word).startsWith('可用'), check.optional?.word)
ok('自检文字列出 Python 版本与七个技能', checkText.includes('Python：可用') && checkText.includes('mqc-legal-chart-master'))

// ---------------------------------------------------------------- 工具：真跑七个技能
section('nlv_run · 七个技能各跑一次示例（在中文带空格的工作区里）')
// Word 版必须靠随插件附带的 docx 写出来：清掉本机的 NODE_PATH，免得用到全局装的那份
delete process.env.NODE_PATH
async function run(skill, script, args, opts = {}) {
  const v = await tools.get('nlv_run').execute({ skill, script, args, ...opts }, exec(opts.cwd || WS))
  return v
}
const cases = [
  ['mqc-litigation-visual-redraw', 'scripts/render.py', ['examples/flowchart.json', 'v1/流程图', '--formats=svg,pptx'], ['.svg', '.pptx']],
  ['mqc-timeline-master', 'scripts/render_figure.py', ['examples/two-sides-numbered.json', 'v2 时间轴.svg'], ['.svg']],
  ['mqc-legal-relation-master', 'scripts/make.py', ['examples/relations-demo.json', '--out', 'v3 关系图'], ['.svg', '.pptx']],
  ['mqc-chronicle-master', 'scripts/pipeline.py', ['examples/case-text-layer.json', '', 'v4 输出'], ['.xlsx', '.docx']],
  ['mqc-trial-confrontation-master', 'scripts/pipeline.py', ['--demo', 'v5'], ['.svg', '.xlsx']],
  ['mqc-legal-chart-master', 'scripts/make.py', ['examples/waffle-outcomes.json', '-o', 'v6/判决结果'], ['.svg', '.pptx']],
  ['mqc-legal-courseware-master', 'scripts/build.py', ['我的课件', '--new', '--title', '民间借贷类案研究'], ['deck.json']],
]
for (const [skill, script, args, want] of cases) {
  const v = await run(skill, script, args)
  const files = v.files || []
  const hit = want.every((ext) => files.some((f) => f.endsWith(ext)))
  ok(`${skill}：退出码 0，写出 ${want.join(' ') || '（只出计划）'}`, v.exitCode === 0 && hit && files.every((f) => f.startsWith(WS)),
    `exit ${v.exitCode}; files ${files.map((f) => f.slice(WS.length)).join(', ')}; stderr ${String(v.stderr).slice(-300)}`)
}
const v6 = await run('mqc-legal-chart-master', 'scripts/make.py', ['examples/waffle-outcomes.json', '-o', 'v6b/图'])
ok('参数里的示例路径（examples/…）自动换成技能目录里的完整路径，并在结果里写明', v6.resolvedArgs?.[0]?.from === 'examples/waffle-outcomes.json' && v6.exitCode === 0)
const v6text = tools.get('nlv_run').output.render({}, v6).map((b) => b.text).join('')
ok('运行结果的文字提示用 present 交付成品', v6text.includes('present') && v6text.includes('退出码 0'))
const abs = await run('mqc-legal-chart-master', join(PKG, 'nlv-skills', 'mqc-legal-chart-master', 'scripts', 'make.py'), ['--check'])
ok('script 写成技能目录内的绝对路径也能跑（脚本打印的下一步命令常这样写）', abs.exitCode === 0, abs.stderr)
const bad = await run('mqc-legal-chart-master', 'scripts/make.py', ['不存在.json'])
ok('脚本自己报错时：不抛异常，照实返回非零退出码与中文报错', bad.exitCode !== 0 && /找不到|未出图/.test(bad.stderr + bad.stdout), bad.stderr)
mkdirSync(join(WS, '子目录'), { recursive: true })
const sub = await run('mqc-legal-chart-master', 'scripts/make.py', ['examples/bar-filings.json', '-o', '图'], { workdir: '子目录' })
ok('workdir：在工作区的子目录里运行，产物落在子目录', sub.exitCode === 0 && (sub.files || []).some((f) => f.startsWith(join(WS, '子目录'))), sub.stderr)

section('nlv_run · 越权与非法输入一律拒绝')
const rejects = async (label, args) => {
  try { await tools.get('nlv_run').execute(args, exec()); ok(label, false, '没有拒绝') } catch (e) { ok(label, /技能|脚本|工作|\.py|找不到|没有/.test(e.message), e.message) }
}
await rejects('运行技能目录之外的脚本（../ 跳出）', { skill: 'mqc-legal-chart-master', script: '../../index.js' })
await rejects('运行不是 .py 的文件', { skill: 'mqc-legal-chart-master', script: 'SKILL.md' })
await rejects('运行不存在的脚本', { skill: 'mqc-legal-chart-master', script: 'scripts/没有.py' })
await rejects('workdir 跳出工作区', { skill: 'mqc-legal-chart-master', script: 'scripts/make.py', args: ['--check'], workdir: '..' })
await rejects('workdir 写成工作区外的绝对路径', { skill: 'mqc-legal-chart-master', script: 'scripts/make.py', args: ['--check'], workdir: tmpdir() })
const outside = join(TMP, 'evil.py')
writeFileSync(outside, 'print(1)\n')
await rejects('script 写成技能目录外的绝对路径', { skill: 'mqc-legal-chart-master', script: outside })
let schemaRejected = false
try { await tools.get('nlv_run').execute({ skill: 'not-a-skill', script: 'scripts/make.py' }, exec()) } catch { schemaRejected = true }
ok('skill 不在七个之内：参数校验直接拒绝', schemaRejected)

// ---------------------------------------------------------------- 底层：取消、超时、Windows 候选
section('取消、超时与找 Python')
const runLib = await import(pathToFileURL(join(PKG, 'lib', 'run.js')).href)
const pyLib = await import(pathToFileURL(join(PKG, 'lib', 'python.js')).href)
const found = await pyLib.findPython()
const sleeper = join(TMP, 'sleep.py')
writeFileSync(sleeper, 'import time\ntime.sleep(30)\n')
const ac = new AbortController()
const t0 = Date.now()
setTimeout(() => ac.abort(), 400)
let abortErr = null
try { await runLib.runScript({ python: found, scriptPath: sleeper, cwd: WS, signal: ac.signal }) } catch (e) { abortErr = e }
ok('用户中止：子进程被结束，几秒内返回「已取消」', abortErr?.name === 'AbortError' && Date.now() - t0 < 8000, abortErr)
const to = await runLib.runScript({ python: found, scriptPath: sleeper, cwd: WS, timeoutSec: 5 })
ok('超时：结束子进程并标明 timedOut', to.timedOut === true && to.exitCode === null && to.durationMs < 15000, JSON.stringify(to).slice(0, 200))
const fakeLocal = join(TMP, 'LocalAppData')
mkdirSync(join(fakeLocal, 'Programs', 'Python', 'Python312'), { recursive: true })
writeFileSync(join(fakeLocal, 'Programs', 'Python', 'Python312', 'python.exe'), '')
const wc = pyLib.candidates('win32', { LOCALAPPDATA: fakeLocal })
ok('Windows：先试 py -3，再试 python、python3，再查 python.org 默认安装目录', wc[0][0] === 'py' && wc[0][1][0] === '-3'
  && wc.some(([c]) => c.endsWith(join('Python312', 'python.exe'))), JSON.stringify(wc))
ok('Windows 候选里没有 python3 打头（PowerShell 里没有这个命令）', wc[0][0] !== 'python3')
const help = pyLib.installHelp('win32')
ok('Windows 安装说明写明勾选 Add python.exe to PATH，并说装完重启 DeepSeek Harness', help.includes('Add python.exe to PATH') && help.includes('退出 DeepSeek Harness'))

// 没有 Python 的电脑：另起一个进程（findPython 有缓存），PATH 清空、NLV_PYTHON 指向不存在的程序
const probeNoPy = join(TMP, 'host', 'nopy.mjs')
writeFileSync(probeNoPy, `
import * as m from 'mqc-nlv-dsh'
const tools = new Map()
m.apply({ tools: { register: (d) => tools.set(d.name, d) }, get: () => undefined })
const v = await tools.get('nlv_run').execute({ skill: 'mqc-legal-chart-master', script: 'scripts/make.py', args: ['--check'] },
  { agent: { session: { header: { cwd: process.cwd() } } }, signal: new AbortController().signal })
const t = tools.get('nlv_run').output.render({}, v).map((b) => b.text).join('')
console.log(JSON.stringify({ reason: v.reason, text: t }))
`)
const r = spawnSync(process.execPath, [probeNoPy], {
  cwd: WS, encoding: 'utf8',
  env: { ...process.env, PATH: join(TMP, 'empty-bin'), Path: join(TMP, 'empty-bin'), NLV_PYTHON: join(TMP, 'no-such-python') },
})
let np = {}
try { np = JSON.parse(r.stdout.trim().split('\n').pop()) } catch { np = { raw: r.stdout + r.stderr } }
ok('没有 Python：nlv_run 不抛错，返回安装说明让模型原样转告', np.reason === 'no-python' && np.text?.includes('原样转告') && np.text?.includes('退出 DeepSeek Harness'), JSON.stringify(np).slice(0, 300))

// ---------------------------------------------------------------- 包的清单
section('插件清单')
ok('dsh.bundle.patch 指向包内的 cordis.patch.yml', pkgJson.dsh?.bundle?.patch === './cordis.patch.yml' && existsSync(join(PKG, 'cordis.patch.yml')))
ok('engines.dsh 写了版本范围', typeof pkgJson.engines?.dsh === 'string' && pkgJson.engines.dsh.length > 0)
ok('许可是 AGPL-3.0-only，包里带 LICENSE 全文', pkgJson.license === 'AGPL-3.0-only' && readFileSync(join(PKG, 'LICENSE'), 'utf8').includes('GNU AFFERO GENERAL PUBLIC LICENSE'))
const suite = JSON.parse(readFileSync(join(PLUGIN, '..', 'mqc-nlv', '.claude-plugin', 'plugin.json'), 'utf8')).version
ok(`插件版本与套件版本一致（${suite}）`, pkgJson.version === suite)
const missing = Object.values(pkgJson.exports).filter((t) => !t.includes('*') && !existsSync(join(PKG, t)))
ok('exports 指向的文件都在包里', missing.length === 0, missing)
for (const lang of ['en', 'zh']) {
  const meta = JSON.parse(readFileSync(join(PKG, 'locale', `${lang}.json`), 'utf8')).meta
  ok(`locale/${lang}.json：标题、描述齐全，详细介绍在 docs/ 子目录且存在`, meta.title && meta.description && meta.detail.startsWith('docs/') && existsSync(join(PKG, meta.detail)))
}
const icon = readFileSync(join(PKG, 'icon.svg'), 'utf8')
ok('图标是自包含的 SVG（无脚本、无文字、无外链；只引用自己内部的渐变与裁切），不超过 256 KB', !/<script|<text|<image|href=|url\((?!#)/i.test(icon) && icon.length < 256 * 1024)
ok('技能目录有自己的 package.json（type: commonjs），里面的 Node 脚本不会被插件的 ES 模块设定带歪',
  JSON.parse(readFileSync(join(PKG, 'nlv-skills', 'package.json'), 'utf8')).type === 'commonjs')
ok('包里带 npm 的 docx（只带打包好的 CommonJS 一个文件与许可）', existsSync(join(PKG, 'nodejs', 'node_modules', 'docx', 'dist', 'index.cjs'))
  && existsSync(join(PKG, 'nodejs', 'node_modules', 'docx', 'LICENSE')) && readFileSync(join(PKG, 'THIRD-PARTY-NOTICES.md'), 'utf8').includes('docx'))
ok('包里有第三方声明与 openpyxl / et_xmlfile 的许可原文', existsSync(join(PKG, 'THIRD-PARTY-NOTICES.md')) && readdirSync(join(PKG, 'python', 'LICENSES')).length >= 2)
ok('带上各技能的自检脚本（大事记、庭审对抗图出图后要调用），不带缓存', existsSync(join(PKG, 'nlv-skills', 'mqc-chronicle-master', 'tests', 'check_deliverables.py'))
  && existsSync(join(PKG, 'nlv-skills', 'mqc-trial-confrontation-master', 'tests', 'cross_check.py'))
  && !existsSync(join(PKG, 'nlv-skills', 'mqc-legal-chart-master', 'scripts', '__pycache__')))
ok('不带只给 README 看的展示图（longform、modes、screenshots、gallery）', !existsSync(join(PKG, 'nlv-skills', 'mqc-litigation-visual-redraw', 'assets', 'longform'))
  && !existsSync(join(PKG, 'nlv-skills', 'mqc-legal-chart-master', 'assets', 'gallery.png')))

rmSync(TMP, { recursive: true, force: true })
console.log(`\n${total - fails}/${total} 项通过`)
process.exit(fails ? 1 : 0)
