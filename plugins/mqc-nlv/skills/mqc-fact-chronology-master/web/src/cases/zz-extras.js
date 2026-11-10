/* 各案的补充数据：证据编号、页数与读取情况、程序状态、叙述线索（由 AI 读材料后归纳，律师可改） */
(function(){
  const C=id=>CASES.find(c=>c.id===id);
  const M=(c,id,o)=>Object.assign(c.materials.find(m=>m.id===id),o);
  let c=C('lending');
  M(c,'L-01',{evno:'原证1',medium:'image',pages:1,read:1,confirm:'已质证'});
  M(c,'L-02',{evno:'原证2',pages:1,read:1,confirm:'已质证'});
  M(c,'L-03',{evno:'原证3',pages:4,read:4});
  M(c,'L-04',{evno:'被证1',pages:2,read:2});
  M(c,'L-05',{evno:'原证4',medium:'image',pages:1,read:1});
  const NARR={"LF01": "李四向张三出具借条，载明借款伍拾万元、借期一年、月利率1.5%", "LF02": "王五在借条保证人处签名，载明承担连带保证责任", "LF03": "张三向李四交付借款", "LF04": "借条载明的借期届满", "LF05": "李四在微信中称「这个月先还5万，过几天转」", "LF06": "李四向张三还款5万元", "LF09": "李四以现金向张三还款", "LF10": "张三在微信中询问李四何时还款", "LF07": "李四在微信中称「下周一先还10万」", "LF08": "李四向张三还款10万元", "LF11": "张三以短信催告李四于6月15日前归还剩余借款", "LF13": "李四在微信中称「剩下的腊月二十前肯定还清」", "LF14": "张三向法院提起诉讼", "LF15": "李四提交答辩状", "LF12": "双方口头约定利息从本金中预先扣除"};
  c.facts.forEach(f=>{ if(NARR[f.id]) f.narr=NARR[f.id]; });
  c.threads=[{id:'t1',title:'借款的成立与交付',facts:['LF01','LF02','LF03','LF04','LF12']},
             {id:'t2',title:'还款',facts:['LF05','LF06','LF09','LF10','LF07','LF08','LF13']},
             {id:'t3',title:'催收与诉讼',facts:['LF11','LF14','LF15']}];
  c=C('lease');
  M(c,'R-01',{evno:'原证1',pages:3,read:3}); M(c,'R-02',{evno:'原证2',medium:'image'}); M(c,'R-03',{evno:'原证3',pages:5,read:5});
  M(c,'R-04',{evno:'原证4',pages:2,read:2}); M(c,'R-05',{evno:'原证5'}); M(c,'R-08',{evno:'被证1'});
  c.threads=[{id:'t1',title:'租约与押金',facts:['RF01','RF02','RF03','RF13']},
             {id:'t2',title:'租金支付',facts:['RF05','RF06','RF07','RF08','RF08w','RF08b','RF08c','RF09']},
             {id:'t3',title:'退租与押金争议',facts:['RF15','RF10','RF11','RF14','RF12']},
             {id:'t4',title:'诉讼',facts:['RF16','RF17']}];
  c=C('tort');
  M(c,'T-01',{evno:'原证1',pages:2,read:2,confirm:'已质证'}); M(c,'T-02',{evno:'原证2',pages:3,read:3}); M(c,'T-03',{evno:'原证3',pages:2,read:2});
  M(c,'T-04',{evno:'原证4',medium:'image',pages:3,read:3}); M(c,'T-05',{evno:'被证1',medium:'image'}); M(c,'T-06',{evno:'原证5',pages:2,read:1});
  M(c,'T-07',{evno:'被证2',pages:2,read:2});
  c.threads=[{id:'t1',title:'事故与责任认定',facts:['TF02','TF11','TF03','TF01']},
             {id:'t2',title:'治疗与费用',facts:['TF04','TF05','TF07','TF06','TF10','TF08']},
             {id:'t3',title:'误工',facts:['TF09']},{id:'t4',title:'诉讼',facts:['TF12','TF13']}];
  c=C('family');
  M(c,'H-01',{evno:'原证1'}); M(c,'H-02',{evno:'原证2',pages:12,read:12}); M(c,'H-03',{evno:'原证3'}); M(c,'H-04',{evno:'原证4',pages:2,read:2});
  M(c,'H-05',{evno:'原证5',pages:6,read:6}); M(c,'H-06',{evno:'原证6',pages:2,read:2});
  c.threads=[{id:'t1',title:'婚姻关系',facts:['HF01','HF11','HF06']},
             {id:'t2',title:'购房与出资',facts:['HF02','HF03','HF04','HF05','HF08']},
             {id:'t3',title:'房贷还款',facts:['HF09','HF07','HF10']},{id:'t4',title:'诉讼',facts:['HF12','HF13']}];
  c=C('sale');
  c.threads=[{id:'t1',title:'合同订立',facts:['SF01','SF03']},{id:'t2',title:'送货与对账',facts:['SF02','SF04','SF05','SF08','SF11']},
             {id:'t3',title:'付款与催款',facts:['SF07','SF09']},{id:'t4',title:'诉讼',facts:['SF10']}];
  c=C('labor');
  c.threads=[{id:'t1',title:'劳动关系的建立',facts:['WF01','WF02','WF04','WF03']},{id:'t2',title:'解除劳动合同',facts:['WF05','WF06','WF07','WF09']},{id:'t3',title:'仲裁',facts:['WF08']}];
})();
