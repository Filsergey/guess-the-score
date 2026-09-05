(function(){
var style=document.createElement('style');
style.textContent=`
.sheet .sheet-teams{display:grid;grid-template-columns:minmax(0,1fr) 48px minmax(0,1fr);align-items:start;gap:8px;margin-top:18px}
.sheet .sheet-team{min-width:0;text-align:center;font-size:16px;font-weight:850;line-height:1.15;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;min-height:112px}
.sheet .sheet-team img{width:72px!important;height:72px!important;max-width:72px;max-height:72px;object-fit:contain;margin:0 auto 10px!important;display:block}
.sheet .sheet-team .crest{width:72px!important;height:72px!important;margin:0 auto 10px!important;flex:0 0 72px}
.sheet .vs{height:72px;display:flex;align-items:center;justify-content:center;color:#8ba1b6;font-size:15px;font-weight:900;padding:0;margin:0}
.sheet .score-row{margin:17px 0 10px;gap:14px}
.sheet .score{width:86px;height:68px;border-radius:18px;font-size:30px}
.sheet .sheet-note{margin-top:12px;margin-bottom:16px}
@media(max-width:390px){
 .sheet .sheet-teams{grid-template-columns:minmax(0,1fr) 42px minmax(0,1fr);gap:5px}
 .sheet .sheet-team{font-size:15px;min-height:104px}
 .sheet .sheet-team img,.sheet .sheet-team .crest{width:64px!important;height:64px!important;max-width:64px;max-height:64px;flex-basis:64px}
 .sheet .vs{height:64px}
}
`;
document.head.appendChild(style);
})();