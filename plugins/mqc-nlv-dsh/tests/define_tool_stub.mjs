// defineTool 的严格替身（没有 DeepSeek Harness 源码时用）。按官方文档《工具编写参考》的约定校验：
// 参数表是隐式开放的对象根，每个属性是值 schema（string/number/integer/boolean/null/array/object/json/oneOf），
// 只有 required: true 一种必填标记；显式对象必须写 additionalProperties；enum 的类型要对。
// 执行前按参数表校验实参，不合规就抛错（真实现抛 ToolArgsError）。
const TYPES = new Set(['string', 'number', 'integer', 'boolean', 'null', 'array', 'object', 'json'])
const ANN = new Set(['description', 'title', 'default', 'examples'])

function compile(spec, path) {
  if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) throw new Error(`${path}: schema 必须是对象`)
  if (spec.oneOf) return { oneOf: spec.oneOf.map((s, i) => compile(s, `${path}.oneOf[${i}]`)) }
  if (!TYPES.has(spec.type)) throw new Error(`${path}: 不支持的 type ${spec.type}`)
  const allowed = new Set([...ANN, 'type', 'enum', 'const', 'required'])
  if (spec.type === 'array') allowed.add('items')
  if (spec.type === 'object') { allowed.add('properties'); allowed.add('additionalProperties') }
  for (const k of Object.keys(spec)) {
    if (!allowed.has(k)) throw new Error(`${path}.${k}: 不支持的键`)
    if (spec[k] === undefined) throw new Error(`${path}.${k}: 值不能是 undefined`)
  }
  if (spec.required !== undefined && spec.required !== true) throw new Error(`${path}.required 只能是 true`)
  if (spec.type === 'object' && typeof spec.additionalProperties !== 'boolean') throw new Error(`${path}: 显式对象必须写 additionalProperties`)
  if (spec.enum) {
    const want = spec.type === 'integer' ? 'number' : spec.type
    if (!Array.isArray(spec.enum) || spec.enum.some((v) => typeof v !== want)) throw new Error(`${path}.enum 类型不对`)
  }
  const node = { type: spec.type }
  if (spec.enum) node.enum = [...spec.enum]
  if (spec.type === 'array' && spec.items) node.items = compile(spec.items, `${path}.items`)
  if (spec.type === 'object') {
    node.properties = {}
    for (const [k, v] of Object.entries(spec.properties || {})) node.properties[k] = compile(v, `${path}.${k}`)
    node.additionalProperties = spec.additionalProperties
  }
  return node
}

function check(node, v, path, errs) {
  if (node.oneOf) { if (node.oneOf.filter((n) => { const e = []; check(n, v, path, e); return !e.length }).length !== 1) errs.push(`${path}: oneOf`); return }
  const t = node.type
  const okType = t === 'json' || (t === 'string' && typeof v === 'string') || (t === 'number' && typeof v === 'number' && Number.isFinite(v))
    || (t === 'integer' && Number.isInteger(v)) || (t === 'boolean' && typeof v === 'boolean') || (t === 'null' && v === null)
    || (t === 'array' && Array.isArray(v)) || (t === 'object' && v && typeof v === 'object' && !Array.isArray(v))
  if (!okType) { errs.push(`${path}: 应为 ${t}`); return }
  if (node.enum && !node.enum.includes(v)) errs.push(`${path}: 不在 ${node.enum.join('/')} 之内`)
  if (t === 'array' && node.items) v.forEach((x, i) => check(node.items, x, `${path}[${i}]`, errs))
}

export function defineTool(o) {
  const props = {}
  const required = []
  for (const [k, spec] of Object.entries(o.parameters || {})) {
    props[k] = compile(spec, k)
    if (spec.required === true) required.push(k)
  }
  const outSchema = compile(o.output.schema, 'output')
  const parameters = { type: 'object', properties: props, required }
  return {
    name: o.name,
    description: o.description,
    parameters,
    output: { schema: outSchema, render: o.output.render },
    async execute(args, exec) {
      const errs = []
      if (!args || typeof args !== 'object') errs.push('参数应为对象')
      for (const k of required) if (args?.[k] === undefined) errs.push(`缺 ${k}`)
      for (const [k, v] of Object.entries(args || {})) if (props[k]) check(props[k], v, k, errs)
      if (errs.length) throw new Error('参数不合规：' + errs.join('；'))
      return o.execute(args, exec)
    },
  }
}
