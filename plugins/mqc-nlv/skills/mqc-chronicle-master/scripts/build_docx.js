const fs=require('fs');
const {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,AlignmentType,
       ShadingType,BorderStyle,HeadingLevel,VerticalAlign,LevelFormat,convertMillimetersToTwip}=require('docx');
const IN=process.argv[2]||'渲染输入.json', OUT=process.argv[3]||'案件大事记-未后处理.docx';
const D=JSON.parse(fs.readFileSync(IN,'utf8'));

const EA="宋体", TITLE_EA="方正小标宋简体", LATIN="Times New Roman";
const F=(ea)=>({ascii:LATIN,hAnsi:LATIN,cs:LATIN,eastAsia:ea,hint:'eastAsia'});          // 中文走 eastAsia，英文数字走 ascii/hAnsi
const run=(t,{ea=EA,size=23,bold=false}={})=>new TextRun({text:t,font:F(ea),size,bold});
const para=(t,o={})=>new Paragraph({alignment:o.align||AlignmentType.LEFT,
    spacing:{line:o.line||240,lineRule:"auto",before:0,after:0,beforeLines:0,afterLines:0},children:[run(t,o)]});

const USABLE=9186;
const COLS=[779,1538,1948,3177,1744];
const HEAD=["序号","日期","事项","主要内容","备注"];

function cell(children,w,shade){
  return new TableCell({width:{size:w,type:WidthType.DXA},verticalAlign:VerticalAlign.CENTER,
    margins:{top:115,bottom:115,left:110,right:110},
    shading:shade?{type:ShadingType.CLEAR,fill:shade,color:"auto"}:undefined,children});
}
const rows=[new TableRow({tableHeader:true,children:HEAD.map((h,i)=>
  cell([para(h,{ea:EA,align:AlignmentType.CENTER})],COLS[i],"F2EFEC"))})];

D.rows.forEach((r,idx)=>{
  const np=(r.note_parts&&r.note_parts.length)?r.note_parts:[""];
  rows.push(new TableRow({children:[
    cell([para(String(idx+1),{align:AlignmentType.CENTER})],COLS[0]),
    cell([para(r.date,{align:AlignmentType.CENTER})],COLS[1]),
    cell([para(r.item,{bold:true,align:AlignmentType.BOTH})],COLS[2]),           // 只把事项标题加黑
    cell([para(r.content,{align:AlignmentType.BOTH})],COLS[3]),
    cell(np.map(t=>para(t,{align:AlignmentType.LEFT})),COLS[4])
  ]}));
});

const doc=new Document({

  sections:[{properties:{page:{margin:{top:convertMillimetersToTwip(24),bottom:convertMillimetersToTwip(24),
      left:convertMillimetersToTwip(24),right:convertMillimetersToTwip(24)}}},
    children:[
      new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:120},
        children:[run(D.case.title,{ea:TITLE_EA,size:44})]}),
      new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:240},
        children:[run(D.case.subtitle,{size:21})]}),
      new Table({columnWidths:COLS,width:{size:USABLE,type:WidthType.DXA},rows,
        borders:{top:{style:BorderStyle.SINGLE,size:8,color:"000000"},
                 bottom:{style:BorderStyle.SINGLE,size:8,color:"000000"},
                 left:{style:BorderStyle.SINGLE,size:8,color:"000000"},
                 right:{style:BorderStyle.SINGLE,size:8,color:"000000"},
                 insideHorizontal:{style:BorderStyle.SINGLE,size:8,color:"000000"},
                 insideVertical:{style:BorderStyle.SINGLE,size:8,color:"000000"}}}),
      ...(D.endnotes||[]).map((e,i)=>new Paragraph({alignment:AlignmentType.LEFT,
          spacing:{line:300,lineRule:"auto",before:i===0?200:0,after:0},
          children:[run("注"+(i+1)+"："+e,{size:21})]}))
    ]}]});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync(OUT,b);console.log('  docx 原始件：'+OUT);});
