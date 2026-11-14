// HTML आणि data.json = network-first (नवीन version लगेच दिसतो); बाकी static files = cache-first
var CACHE="cs-v2";
var SHELL=["./","./index.html","./manifest.json","./icon.svg"];
self.addEventListener("install",function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(SHELL)}).then(function(){return self.skipWaiting()}));
});
self.addEventListener("activate",function(e){
  e.waitUntil(caches.keys().then(function(ks){
    return Promise.all(ks.filter(function(k){return k!==CACHE}).map(function(k){return caches.delete(k)}));
  }).then(function(){return self.clients.claim()}));
});
function networkFirst(req){
  return fetch(req).then(function(r){
    var cp=r.clone();caches.open(CACHE).then(function(c){c.put(req,cp)});return r;
  }).catch(function(){return caches.match(req,{ignoreSearch:true})});
}
self.addEventListener("fetch",function(e){
  if(e.request.method!=="GET")return;
  var url=new URL(e.request.url);
  if(e.request.mode==="navigate"||url.pathname.endsWith("/")||url.pathname.endsWith(".html")||url.pathname.indexOf("data.json")>-1){
    e.respondWith(networkFirst(e.request));return;
  }
  e.respondWith(caches.match(e.request).then(function(m){return m||fetch(e.request)}));
});
