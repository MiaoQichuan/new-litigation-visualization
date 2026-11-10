/* =====================================================================
   V8 · 内核常量（与案由无关）
   ===================================================================== */
const KIND = {
  statement:{n:'当事人陈述', short:'陈述', shape:'circle', rank:1},
  record:   {n:'书证',       short:'书证', shape:'square', rank:4},
  edata:    {n:'电子数据',   short:'电子数据', shape:'square', rank:3},
  testimony:{n:'证人证言',   short:'证言', shape:'triangle', rank:2}
};
const CONFIRM = ['未提交','已提交','已质证','法院认定','生效确认','未被采纳'];
const STAGES = ['接受咨询','谈案','庭前','庭审时','庭后','结案后'];
/* 内核事件类型：任何案由都有；领域包可改名、可追加 */
const CORE_TYPES = {
  comm:    {n:'沟通往来',   c:'#3C6DB4'},
  meeting: {n:'会议与会谈', c:'#14897F'},
  agree:   {n:'协议或约定', c:'#5A4DB3'},
  pay:     {n:'款项往来',   c:'#C9961E'},
  perf:    {n:'履行',       c:'#3A8445'},
  notice:  {n:'通知与催告', c:'#C24E7C'},
  decision:{n:'决定与审批', c:'#8E4FA0'},
  filing:  {n:'诉讼程序',   c:'#3D4B5E'},
  other:   {n:'其他',       c:'#8E8C85'}
};
const CORE_ORDER = ['comm','meeting','agree','pay','perf','notice','decision','filing','other'];
const CASES = [];
