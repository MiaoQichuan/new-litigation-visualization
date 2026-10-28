// 环境自检用到的小工具：在 PATH 里找程序、找 LibreOffice、找会遮住插件技能的旧副本。

import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { delimiter, join } from 'node:path'

/** 在 PATH 里找一个程序（Windows 按 PATHEXT 补扩展名）。找不到返回 null。 */
export function which(name, env = process.env, platform = process.platform) {
  const dirs = String(env.PATH || env.Path || '').split(delimiter).filter(Boolean)
  const exts = platform === 'win32' ? String(env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';').filter(Boolean) : ['']
  for (const d of dirs) {
    for (const e of exts) {
      const p = join(d, name + e)
      if (existsSync(p)) return p
    }
  }
  return null
}

/** LibreOffice 常不在 PATH 里：再查默认安装位置。 */
export function findSoffice(env = process.env, platform = process.platform) {
  const hit = which('soffice', env, platform) || which('libreoffice', env, platform)
  if (hit) return hit
  const cands = platform === 'win32'
    ? [env.ProgramFiles, env['ProgramFiles(x86)']].filter(Boolean).map((b) => join(b, 'LibreOffice', 'program', 'soffice.exe'))
    : platform === 'darwin' ? ['/Applications/LibreOffice.app/Contents/MacOS/soffice'] : []
  return cands.find((p) => existsSync(p)) || null
}

/**
 * 用户以前手动装过的同名技能（.dsh/skills、.agents/skills）。DeepSeek Harness 让这些位置优先于插件自带的技能，
 * 旧副本会把插件版遮住，而旧副本里的命令写的是 python3（Windows 上没有）。
 */
export function shadowingCopies(names, cwd, env = process.env) {
  const roots = []
  if (cwd) roots.push(join(cwd, '.dsh', 'skills'), join(cwd, '.agents', 'skills'))
  const home = homedir()
  roots.push(join(env.DSH_HOME || join(home, '.dsh'), 'skills'))
  roots.push(join(env.DSH_AGENTS_HOME || join(home, '.agents'), 'skills'))
  const hits = []
  for (const r of roots) {
    for (const n of names) {
      const p = join(r, n, 'SKILL.md')
      if (existsSync(p)) hits.push(join(r, n))
    }
  }
  return hits
}

/** 读 JSON 文件；读不到返回 fallback。 */
export function readJson(p, fallback = null) {
  try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return fallback }
}
