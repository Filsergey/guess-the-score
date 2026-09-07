(()=>{
const css=document.createElement('style');
css.textContent=`
/* Large collectible achievement artwork */
.ach-carousel-shell{margin:0 -10px 2px!important}
.ach-carousel{scroll-padding-inline:16px!important;padding:3px 16px 14px!important;gap:12px!important}
.ach-showcase{flex:0 0 calc(100vw - 36px)!important;max-width:390px!important}
.ach-showcase-inner{padding-left:16px!important;padding-right:16px!important}
.ach-showcase-art-wrap{
  width:calc(100% - 20px)!important;
  max-width:310px!important;
  height:auto!important;
  aspect-ratio:1/1!important;
  margin:12px auto 11px!important;
  border-radius:36px!important;
}
.ach-showcase-art{
  width:calc(100% - 10px)!important;
  height:calc(100% - 10px)!important;
  border-radius:31px!important;
}
.ach-showcase-lock{right:2px!important;bottom:2px!important;width:36px!important;height:36px!important;font-size:17px!important}
@media(max-width:380px){
  .ach-showcase{flex-basis:calc(100vw - 30px)!important}
  .ach-carousel{padding-left:15px!important;padding-right:15px!important;scroll-padding-inline:15px!important}
  .ach-showcase-inner{padding-left:14px!important;padding-right:14px!important}
  .ach-showcase-art-wrap{width:calc(100% - 16px)!important;max-width:none!important}
}
`;
document.head.appendChild(css);
})();
