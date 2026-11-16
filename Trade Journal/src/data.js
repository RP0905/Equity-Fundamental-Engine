export const trades=[
 {id:'TR-4029',userId:'demo',date:'2026-08-14T09:42',entryTime:'2026-08-14T09:42:00Z',exitTime:'2026-08-14T10:02:00Z',volume:47029,symbol:'NQ',side:'Long',entry:23514.25,exit:23542.75,pnl:712,fees:8,r:2.1,strategy:'ORB Continuation',tags:['A+ Setup','Patience'],emotion:'Focused',rating:5,qty:2},
 {id:'TR-4028',userId:'demo',date:'2026-08-14T10:18',entryTime:'2026-08-14T10:18:00Z',exitTime:'2026-08-14T10:36:00Z',volume:12845,symbol:'ES',side:'Short',entry:6422.5,exit:6428.25,pnl:-288,fees:6,r:-0.8,strategy:'Mean Reversion',tags:['Early Entry','FOMO'],emotion:'Impatient',rating:2,qty:2},
 {id:'TR-4027',date:'2026-08-13T09:35',symbol:'NQ',side:'Long',entry:23410,exit:23432,pnl:548,fees:8,r:1.8,strategy:'ORB Continuation',tags:['A+ Setup','Momentum'],emotion:'Confident',rating:5,qty:2},
 {id:'TR-4026',date:'2026-08-13T11:03',symbol:'CL',side:'Short',entry:63.81,exit:63.94,pnl:-260,fees:5,r:-1,strategy:'Pullback',tags:['Moved Stop','Fear'],emotion:'Anxious',rating:1,qty:2},
 {id:'TR-4025',date:'2026-08-12T09:47',symbol:'ES',side:'Long',entry:6408,exit:6418,pnl:495,fees:6,r:1.6,strategy:'ORB Continuation',tags:['A+ Setup','Patience'],emotion:'Focused',rating:4,qty:3},
 {id:'TR-4024',date:'2026-08-12T10:32',symbol:'NQ',side:'Short',entry:23385,exit:23376,pnl:223,fees:8,r:0.7,strategy:'Reversal',tags:['Reversal','Confidence'],emotion:'Calm',rating:4,qty:1},
 {id:'TR-4023',date:'2026-08-11T09:31',symbol:'NQ',side:'Long',entry:23312,exit:23298,pnl:-350,fees:8,r:-1,strategy:'ORB Continuation',tags:['FOMO','Oversized'],emotion:'Frustrated',rating:1,qty:2},
 {id:'TR-4022',date:'2026-08-11T13:19',symbol:'ES',side:'Long',entry:6390,exit:6399,pnl:445,fees:6,r:1.4,strategy:'Pullback',tags:['Pullback','Patience'],emotion:'Focused',rating:4,qty:2},
 {id:'TR-4021',date:'2026-08-08T09:38',symbol:'CL',side:'Short',entry:64.19,exit:64.03,pnl:320,fees:5,r:1.2,strategy:'Reversal',tags:['A+ Setup','Reversal'],emotion:'Calm',rating:5,qty:2},
 {id:'TR-4020',date:'2026-08-08T10:04',symbol:'NQ',side:'Long',entry:23280,exit:23271,pnl:-225,fees:8,r:-.7,strategy:'Momentum',tags:['Late Entry','FOMO'],emotion:'Impatient',rating:2,qty:1}
];
export const nav=[['Overview','/dashboard','⌁'],['Trades','/trades','⇄'],['Journal','/journal','✎'],['Analytics','/analytics','◫'],['Strategies','/strategies','◎'],['Calendar','/calendar','▦'],['Intelligence','/insights','✦'],['Settings','/settings','⚙']];
// Development-only provider normalization. Replace this module with an API repository in production.
trades.forEach(t=>{t.userId??='demo';t.entryTime??=`${t.date}:00Z`;t.exitTime??=new Date(new Date(t.entryTime).getTime()+18*60000).toISOString();t.volume??=Math.abs((t.quantity??t.qty??1)*(t.entryPrice??t.entry??0));});
// Manual demo entries are persisted separately from the immutable seed dataset.
try{const saved=JSON.parse(localStorage.getItem('arc-manual-trades')||'[]');if(Array.isArray(saved))trades.unshift(...saved)}catch{}
