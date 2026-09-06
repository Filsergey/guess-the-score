(()=>{
const s=document.createElement('style');
s.textContent=`
#leaguesView .league-card{--neutral-bg1:rgba(18,43,73,.96);--neutral-bg2:rgba(8,20,34,.98);background:linear-gradient(145deg,var(--neutral-bg1),var(--neutral-bg2))!important}
#leaguesView .league-card[data-tournament]{background:linear-gradient(145deg,var(--neutral-bg1),var(--neutral-bg2))!important}
#leaguesView .league-card.selected{background:linear-gradient(145deg,rgba(17,43,77,.99),rgba(6,20,39,.99))!important}
#leaguesView .league-card[data-tournament='39'].selected{background:linear-gradient(145deg,rgba(28,34,63,.99),rgba(12,18,37,.99))!important}
#leaguesView .league-card[data-tournament='140'].selected{background:linear-gradient(145deg,rgba(38,30,43,.99),rgba(17,17,28,.99))!important}
#leaguesView .league-card[data-tournament='135'].selected{background:linear-gradient(145deg,rgba(18,42,69,.99),rgba(8,20,34,.99))!important}
#leaguesView .league-card[data-tournament='78'].selected{background:linear-gradient(145deg,rgba(37,31,38,.99),rgba(18,17,26,.99))!important}
#leaguesView .league-card .league-emblem{background:rgba(15,34,54,.82)!important}
#leaguesView .league-card .league-edit{background:rgba(var(--accent-rgb),.09)!important}
#leaguesView .league-card .league-owner,#leaguesView .league-card .league-role{background:rgba(var(--accent-rgb),.10)!important}
#leaguesView .league-card.selected .league-emblem{box-shadow:0 0 10px rgba(var(--accent-rgb),.18)}

/* Owner badge sits in the same right column as the management button. */
#leaguesView .league-card:has(.league-owner){min-height:82px!important;padding-right:122px!important}
#leaguesView .league-card .league-owner{position:absolute!important;right:11px!important;top:10px!important;width:98px!important;height:17px!important;margin:0!important;padding:0 6px!important;display:flex!important;align-items:center!important;justify-content:center!important;border-radius:6px!important;font-size:6.5px!important;line-height:1!important;letter-spacing:.05em!important;text-align:center!important;white-space:nowrap!important;z-index:4!important}
#leaguesView .league-card:has(.league-owner) .league-edit.gts-league-manage{right:11px!important;top:auto!important;bottom:10px!important;width:98px!important;min-width:98px!important;height:29px!important;transform:none!important}
#leaguesView .league-card:has(.league-owner) .league-edit.gts-league-manage:active{transform:scale(.97)!important}
@media(max-width:430px){
 #leaguesView .league-card:has(.league-owner){min-height:78px!important;padding-right:114px!important}
 #leaguesView .league-card .league-owner{right:10px!important;top:9px!important;width:92px!important;height:16px!important;font-size:6.2px!important}
 #leaguesView .league-card:has(.league-owner) .league-edit.gts-league-manage{right:10px!important;bottom:9px!important;width:92px!important;min-width:92px!important;height:27px!important}
}
`;
document.head.appendChild(s);
})();