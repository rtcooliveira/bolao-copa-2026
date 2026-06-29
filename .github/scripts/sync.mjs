const BASE="https://bolao-copa-2026-c99d8-default-rtdb.firebaseio.com/boloes/b_1780403890548_ucnw8";
const EN2PT={"South Africa":"África do Sul","Canada":"Canadá","Germany":"Alemanha","Paraguay":"Paraguai","Netherlands":"Holanda","Morocco":"Marrocos","Brazil":"Brasil","Japan":"Japão","France":"França","Sweden":"Suécia","Ivory Coast":"Costa do Marfim","Norway":"Noruega","Mexico":"México","Ecuador":"Equador","England":"Inglaterra","Congo DR":"RD Congo","DR Congo":"RD Congo","United States":"EUA","Bosnia-Herzegovina":"Bósnia-Herzegovina","Belgium":"Bélgica","Senegal":"Senegal","Portugal":"Portugal","Croatia":"Croácia","Spain":"Espanha","Austria":"Áustria","Switzerland":"Suíça","Algeria":"Argélia","Argentina":"Argentina","Cape Verde":"Cabo Verde","Colombia":"Colômbia","Ghana":"Gana","Australia":"Austrália","Egypt":"Egito"};
const KO_NEXT_W={M89:["M74","M77"],M90:["M73","M75"],M91:["M76","M78"],M92:["M79","M80"],M93:["M83","M84"],M94:["M81","M82"],M95:["M86","M88"],M96:["M85","M87"],M97:["M89","M90"],M98:["M93","M94"],M99:["M91","M92"],M100:["M95","M96"],M101:["M97","M98"],M102:["M99","M100"],M104:["M101","M102"]};
const KO_NEXT_L={M103:["M101","M102"]};
const g=async p=>(await fetch(BASE+p+".json")).json();
(async()=>{
  let ko=await g("/realResults/knockout")||{};
  const pair={};
  for(const m of Object.keys(ko)){const v=ko[m];if(v&&v.hTeam&&v.aTeam)pair[[v.hTeam,v.aTeam].sort().join("|")]=m;}
  const dates=[];let d=new Date(Date.UTC(2026,5,28));const end=new Date(Date.UTC(2026,6,19));
  while(d<=end){dates.push(d.toISOString().slice(0,10).replace(/-/g,""));d=new Date(d.getTime()+864e5);}
  const written=[];
  for(const ds of dates){
    let evs;
    try{const j=await (await fetch("https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates="+ds)).json();evs=j.events||[];}catch(e){continue;}
    for(const e of evs){
      const c=e.competitions[0];const st=(c.status&&c.status.type)||{};
      const finished=st.completed===true||st.name==="STATUS_FULL_TIME"||st.name==="STATUS_FINAL";
      if(!finished)continue;
      const h=c.competitors.find(x=>x.homeAway==="home"),a=c.competitors.find(x=>x.homeAway==="away");
      const hpt=EN2PT[h.team.displayName],apt=EN2PT[a.team.displayName];
      if(!hpt||!apt)continue;
      const mid=pair[[hpt,apt].sort().join("|")];if(!mid)continue;
      const slot=ko[mid];
      let home,away,hWin,aWin;
      if(slot.hTeam===hpt){home=+h.score;away=+a.score;hWin=h.winner===true;aWin=a.winner===true;}
      else{home=+a.score;away=+h.score;hWin=a.winner===true;aWin=h.winner===true;}
      let winner=null,pen=null;
      if(hWin&&!aWin)winner=slot.hTeam;else if(aWin&&!hWin)winner=slot.aTeam;else if(home>away)winner=slot.hTeam;else if(away>home)winner=slot.aTeam;
      if(!winner)continue;
      if(home===away)pen=winner;
      const obj={hTeam:slot.hTeam,aTeam:slot.aTeam,home,away,winner};if(pen)obj.penaltyWinner=pen;
      const cur=ko[mid];
      const same=cur&&cur.home===obj.home&&cur.away===obj.away&&cur.winner===obj.winner&&(cur.penaltyWinner||null)===(obj.penaltyWinner||null);
      if(same)continue;
      await fetch(BASE+"/realResults/knockout/"+mid+".json",{method:"PUT",body:JSON.stringify(obj)});
      ko[mid]=obj;written.push(mid+" "+slot.hTeam+" "+home+"x"+away+" "+slot.aTeam+" ("+winner+")");
    }
  }
  const winOf=m=>(ko[m]&&ko[m].winner)||null;
  const loseOf=m=>{const x=ko[m];if(!x||!x.winner)return null;return x.winner===x.hTeam?x.aTeam:x.hTeam;};
  const seeded=[];
  const seed=async(id,hh,aa)=>{if(hh&&aa&&!(ko[id]&&ko[id].hTeam)){await fetch(BASE+"/realResults/knockout/"+id+".json",{method:"PATCH",body:JSON.stringify({hTeam:hh,aTeam:aa})});ko[id]=Object.assign({},ko[id]||{},{hTeam:hh,aTeam:aa});seeded.push(id+": "+hh+" x "+aa);}};
  for(const id of Object.keys(KO_NEXT_W)){const p=KO_NEXT_W[id];await seed(id,winOf(p[0]),winOf(p[1]));}
  for(const id of Object.keys(KO_NEXT_L)){const p=KO_NEXT_L[id];await seed(id,loseOf(p[0]),loseOf(p[1]));}
  console.log("WRITTEN:",written.length?written.join(" | "):"(nada novo)");
  console.log("SEEDED:",seeded.length?seeded.join(" | "):"(nada)");
})().catch(e=>{console.error(e);process.exit(1);});
