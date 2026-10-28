// 新诉讼可视化 · DeepSeek Harness 插件：把随包的七个技能注册给 DeepSeek Harness。
//
// 每个技能的正文 = 一段「在 DeepSeek Harness 里怎么跑」的前言 + 原样的 SKILL.md 正文（去掉开头的 YAML）。
// 技能目录（scripts/、references/、examples/……）作为 resourceBase 交给模型，相对路径照常可读。
//
// Copyright (C) 2026 缪奇川（Miao Qichuan）. AGPL-3.0-only.

import { readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { readJson } from './lib/env.js'

export const name = 'mqc-nlv-dsh-skills'
export const inject = ['skills']

const PROVIDER = 'mqc-nlv'
const ROOT = dirname(fileURLToPath(import.meta.url))
const SKILLS_ROOT = join(ROOT, 'nlv-skills')
const PREAMBLE_PATH = join(ROOT, 'lib', 'preamble.md')
// 与 @deepseek-ai/dsh-skill 的 BUNDLED_SKILL_RANK 相同：随包技能的标准优先级（数值大者让位于用户自己装的技能）
const BUNDLED_RANK = 600
const INVOCATION = Object.freeze({ modelInvocable: true, userInvocable: true })

/** 去掉开头的 YAML 头（--- … ---），只留正文。 */
export function stripFrontmatter(text) {
  const t = text.replace(/^﻿/, '')
  if (!t.startsWith('---')) return t.trim()
  const end = t.indexOf('\n---', 3)
  if (end < 0) return t.trim()
  const after = t.indexOf('\n', end + 4)
  return (after < 0 ? '' : t.slice(after + 1)).trim()
}

export function candidatesFrom(manifest) {
  return manifest.skills.map((s) => {
    const dir = join(SKILLS_ROOT, s.name)
    return Object.freeze({
      name: s.name,
      description: s.description,
      invocation: INVOCATION,
      provider: PROVIDER,
      source: 'bundled',
      path: join(dir, 'SKILL.md'),
      resourceBase: Object.freeze({ kind: 'directory', path: dir }),
      rank: BUNDLED_RANK,
      locator: s.name,
    })
  })
}

export async function loadContent(candidate) {
  const [preamble, body] = await Promise.all([
    readFile(PREAMBLE_PATH, 'utf8'),
    readFile(candidate.path, 'utf8'),
  ])
  return preamble.replaceAll('{{skill}}', candidate.name).trim() + '\n\n---\n\n' + stripFrontmatter(body)
}

export function makeProvider(manifest = readJson(join(SKILLS_ROOT, 'skills.json'), { skills: [] })) {
  const candidates = candidatesFrom(manifest)
  return {
    name: PROVIDER,
    list: () => Promise.resolve(candidates),
    async get(candidate) {
      const c = candidates.find((x) => x.name === candidate.name) || candidate
      return {
        name: c.name,
        description: c.description,
        invocation: c.invocation,
        provider: c.provider,
        source: c.source,
        path: c.path,
        resourceBase: c.resourceBase,
        content: await loadContent(c),
      }
    },
  }
}

export function apply(ctx) {
  const provider = makeProvider()
  ctx.skills.registerProvider(() => provider)
}
