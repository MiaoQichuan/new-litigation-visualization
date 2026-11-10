/* 刁难件 E1：全部无日期 —— 答案：5 个事实全部进无日期栏，时间线显示空状态，不报错 */
CASES.push({id:'edge-undated',title:'刁难件：全部无日期',cause:'（测试）',pack:'general',program:'—',unit:'元',test:'刁难 · 全部无日期',parties:[],note:'',
 materials:[
  {id:'U-01',name:'情况说明',kind:'statement',sub:'情况说明',side:'委托人',date:'未载',dsrc:'无落款',stage:0,confirm:'未提交',lines:['#情况说明','我和对方是多年朋友。','对方说会帮我办好这件事。','后来他就不接电话了。']},
  {id:'U-02',name:'聊天截图',kind:'edata',sub:'聊天截图',side:'双方',date:'未载',dsrc:'无',stage:0,confirm:'未提交',lines:['#聊天截图','对方：放心，包在我身上。','我：钱已经给你了。']},
  {id:'U-03',name:'证人说明',kind:'testimony',sub:'证人说明',side:'证人',date:'未载',dsrc:'无',stage:0,confirm:'未提交',lines:['#证人说明','我看到委托人把一个信封交给对方。']}],
 actors:{},inferences:{},
 facts:[
  {id:'UF1',t:'other',title:'双方是多年朋友',state:'occ',recs:[{d:'U-01',loc:'第1段',q:'我和对方是多年朋友。',raw:'未载',p:'none'}]},
  {id:'UF2',t:'comm',title:'对方承诺帮忙办事',state:'occ',recs:[{d:'U-01',loc:'第2段',q:'对方说会帮我办好这件事。',raw:'未载',p:'none'},{d:'U-02',loc:'对方',q:'对方：放心，包在我身上。',raw:'未载',p:'none'}]},
  {id:'UF3',t:'pay',title:'委托人交付款项',state:'occ',recs:[{d:'U-02',loc:'我',q:'我：钱已经给你了。',raw:'未载',p:'none'},{d:'U-03',loc:'第1段',q:'我看到委托人把一个信封交给对方。',raw:'未载',p:'none'}]},
  {id:'UF4',t:'comm',title:'对方不再接电话',state:'occ',recs:[{d:'U-01',loc:'第3段',q:'后来他就不接电话了。',raw:'未载',p:'none'}]}],
 claims:[],relations:[],attention:[],
 answer:{conflicts:[],amountConflicts:[],undated:['UF1','UF2','UF3','UF4'],suspects:[],inferTypes:[],packRules:[],stmtOnly:['UF1','UF4']}});

/* 刁难件 E2：只有一份判决书，同一天十件事 —— 答案：无冲突；同日事件聚合成数字圈，可放大 */
(()=>{ const lines=['#民事判决书（节选）']; const facts=[]; let k=0;
 const day=['2024年5月8日'];
 const items=['原告提交起诉状','法院受理','原告申请财产保全','法院作出保全裁定','原告交纳诉讼费','法院向被告送达起诉状副本','法院送达举证通知书','法院送达开庭传票','被告提出管辖权异议','法院组织证据交换'];
 items.forEach((t,i)=>{ const q=`${day[0]}，${t}。`; lines.push(q); facts.push({id:'JF'+(++k),t:'filing',title:t,state:'occ',recs:[{d:'J-01',loc:'本院查明',q,raw:day[0],s:'2024-05-08',p:'day'}]}); });
 ['2024年6月3日，本院公开开庭审理。','2024年7月15日，本院第二次开庭。','2024年9月2日，本院作出判决。'].forEach((q,i)=>{ lines.push(q); const m=q.match(/(\d+)年(\d+)月(\d+)日/); facts.push({id:'JF'+(++k),t:'filing',title:q.split('，')[1].replace('。',''),state:'occ',key:i===2?1:0,recs:[{d:'J-01',loc:'本院查明',q,raw:`${m[1]}年${m[2]}月${m[3]}日`,s:`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`,p:'day'}]}); });
 CASES.push({id:'edge-single',title:'刁难件：一份判决书、同日十件事',cause:'（测试）',pack:'general',program:'一审',unit:'元',test:'刁难 · 单份材料',parties:[],note:'',
  materials:[{id:'J-01',name:'民事判决书',kind:'record',sub:'民事判决书',side:'法院',date:'2024年9月2日',dsrc:'落款',stage:4,confirm:'法院认定',lines}],
  actors:{},inferences:{},facts,claims:[],relations:[],attention:[],
  answer:{conflicts:[],amountConflicts:[],undated:[],suspects:[],inferTypes:[],packRules:[],stmtOnly:[]}}); })();

/* 刁难件 E3：压力测试 —— 十年、8 份材料、220 个事实，其中第 7、47、87… 号（每 40 个）有日期冲突，每 55 个有金额冲突。
   用固定种子生成，答案由生成器同步写出。 */
(()=>{ let seed=7; const rnd=()=>{ seed=(seed*1103515245+12345)%2147483648; return seed/2147483648; };
 const kinds=['record','record','edata','statement','testimony','record','statement','record'];
 const mats=kinds.map((k,i)=>({id:'X-'+String(i+1).padStart(2,'0'),name:'材料'+(i+1),kind:k,sub:['合同','日志','聊天','起诉状','证言','回单','答辩','函件'][i],side:'—',date:'—',dsrc:'—',stage:Math.min(2,Math.floor(i/3)),confirm:'已提交',lines:['#材料'+(i+1)]}));
 const types=['comm','meeting','agree','pay','perf','notice','decision','filing','other'];
 const facts=[], conf=[], amc=[], undated=[]; const start=Date.UTC(2015,0,1)/864e5;
 const iso=n=>new Date(n*864e5).toISOString().slice(0,10);
 for(let i=1;i<=220;i++){
   const id='XF'+String(i).padStart(3,'0'); const base= i%9===0 ? start+Math.floor(i/9)*160 : start+Math.floor(rnd()*3650);
   const d1=iso(base); const di=Math.floor(rnd()*8), dj=(di+1+Math.floor(rnd()*7))%8;
   const q1=`第${i}项：${d1} 发生事项${i}。`; mats[di].lines.push(q1);
   const recs=[{d:mats[di].id,loc:'第'+i+'项',q:q1,raw:d1,s:d1,p:'day'}];
   if(i%40===7){ const d2=iso(base+3+Math.floor(rnd()*20)); const q2=`第${i}项另载：${d2} 发生事项${i}。`; mats[dj].lines.push(q2); recs.push({d:mats[dj].id,loc:'第'+i+'项',q:q2,raw:d2,s:d2,p:'day'}); conf.push(id); }
   else if(i%3===0){ const q2=`第${i}项印证：${d1}。`; mats[dj].lines.push(q2); recs.push({d:mats[dj].id,loc:'第'+i+'项',q:q2,raw:d1,s:d1,p:'day'}); }
   if(i%55===10){ recs.forEach((r,k)=>r.amt=100+k*7); if(recs.length===1){ const q3=`第${i}项金额另载。`; mats[dj].lines.push(q3); recs.push({d:mats[dj].id,loc:'第'+i+'项',q:q3,raw:d1,s:d1,p:'day',amt:93}); } amc.push(id); }
   if(i%50===0){ recs.forEach(r=>{ r.p='none'; delete r.s; r.raw='未载'; }); undated.push(id); const c=conf.indexOf(id); if(c>=0) conf.splice(c,1); }
   facts.push({id,t:types[i%types.length],title:`事项 ${i}${i%13===0?'：一个特别长的事实标题，用来测试截断和省略号是否正常':''}`,state:i%17===0?'agr':'occ',key:i%60===0?1:0,recs});
 }
 const stmtOnly=facts.filter(f=>f.t!=='filing' && f.recs.every(r=>mats.find(m=>m.id===r.d).kind==='statement')).map(f=>f.id);
 CASES.push({id:'edge-stress',title:'刁难件：十年 220 个事实',cause:'（测试）',pack:'general',program:'—',unit:'万元',test:'刁难 · 压力',parties:[],note:'',
  materials:mats,actors:{},inferences:{},facts,claims:[],relations:[],attention:[],
  answer:{conflicts:conf,amountConflicts:amc,undated,suspects:[],inferTypes:[],packRules:[],stmtOnly}}); })();
