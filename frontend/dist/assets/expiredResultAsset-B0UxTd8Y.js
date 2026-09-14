import{d0 as n,dX as f}from"./index-BifiXCp8.js";import{r as a,o as u,b as h,c as m}from"./vue-CWetpzS1.js";function o(e,t){return typeof document>"u"?t:getComputedStyle(document.documentElement).getPropertyValue(e).trim()||t}function x(){const e=n()==="midnight",t=e?"#2c2c2c":o("--theme-page-base","#fffaf4"),r=e?"#252526":o("--theme-panel-bg-strong","#ffe6c8"),i=e?"#a8a8a8":o("--theme-panel-border-strong","#efc784"),d=e?"#ffffff":o("--theme-accent","#d08a24"),c=e?"#e6e6e6":o("--theme-accent-strong","#ffd585"),l=e?"#ffffff":o("--theme-title","#8c5a16"),s=e?"#d0d0d0":o("--theme-text-secondary","#a9742e");return`data:image/svg+xml;charset=UTF-8,${encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="960" viewBox="0 0 960 960">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${t}"/>
      <stop offset="100%" stop-color="${r}"/>
    </linearGradient>
  </defs>
  <rect width="960" height="960" rx="56" fill="url(#bg)"/>
  <rect x="74" y="74" width="812" height="812" rx="42" fill="none" stroke="${i}" stroke-dasharray="18 16" stroke-width="10"/>
  <g fill="none" stroke="${d}" stroke-linecap="round" stroke-linejoin="round">
    <rect x="282" y="248" width="396" height="286" rx="28" stroke-width="18"/>
    <path d="M326 490l110-108 92 88 72-66 76 86" stroke-width="18"/>
    <circle cx="400" cy="330" r="34" fill="${c}" stroke-width="12"/>
  </g>
  <text x="480" y="654" text-anchor="middle" font-size="54" font-weight="700" fill="${l}">原图已过期</text>
  <text x="480" y="726" text-anchor="middle" font-size="34" fill="${s}">服务器保留原图15天</text>
  <text x="480" y="776" text-anchor="middle" font-size="34" fill="${s}">请在有效期内查看或下载</text>
</svg>
`)}`}function w(){const e=a(n());let t=null;const r=m(()=>(e.value,x()));return u(()=>{e.value=n(),t=new MutationObserver(()=>{e.value=n()}),t.observe(document.documentElement,{attributes:!0,attributeFilter:[f]})}),h(()=>{t==null||t.disconnect(),t=null}),r}export{w as u};
