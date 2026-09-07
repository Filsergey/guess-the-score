(()=>{
const css=document.createElement('style');
css.textContent=`
/* Large achievement cards, constrained to the sheet */
.ach-content,.ach-wrap,.ach-carousel-shell{max-width:100%!important;box-sizing:border-box!important}
.ach-content,.ach-wrap,.ach-carousel-shell{overflow-x:hidden!important}
.ach-carousel-shell{width:100%!important;margin:0!important}
.ach-carousel{
  width:100%!important;
  box-sizing:border-box!important;
  padding:3px 10px 14px!important;
  scroll-padding-inline:10px!important;
  gap:12px!important;
  overflow-x:auto!important;
  overflow-y:hidden!important;
}
.ach-showcase{
  flex:0 0 92%!important;
  width:auto!important;
  max-width:none!important;
  min-width:0!important;
  box-sizing:border-box!important;
}
.ach-showcase-inner{
  box-sizing:border-box!important;
  width:100%!important;
  padding-left:14px!important;
  padding-right:14px!important;
}
.ach-showcase-art-wrap{
  width:calc(100% - 24px)!important;
  max-width:none!important;
  height:auto!important;
  aspect-ratio:1/1!important;
  margin:12px auto 11px!important;
  border-radius:34px!important;
  box-sizing:border-box!important;
  overflow:hidden!important;
}
.ach-showcase-art{
  width:calc(100% - 8px)!important;
  height:calc(100% - 8px)!important;
  border-radius:30px!important;
  object-fit:cover!important;
  object-position:center!important;
  transform:none!important;
}
.ach-showcase-lock{
  right:3px!important;
  bottom:3px!important;
  width:36px!important;
  height:36px!important;
  font-size:17px!important;
}
@media(max-width:380px){
  .ach-carousel{padding-left:8px!important;padding-right:8px!important;scroll-padding-inline:8px!important}
  .ach-showcase{flex-basis:93%!important}
  .ach-showcase-inner{padding-left:12px!important;padding-right:12px!important}
  .ach-showcase-art-wrap{width:calc(100% - 18px)!important}
}
`;
document.head.appendChild(css);
})();
