var CACHE="cs-v1";
var SHELL=["./","./index.html","./manifest.json","./icon.svg"];
self.addEventListener("install",function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(SHELL)}).then(function(){return self.skipWaiting()}));
});
self.addEventListener("activate",function(e){
  e.waitUntil(caches.keys().then(function(ks){
    return Promise.all(ks.filter(function(k){return k!==CACHE}).map(function(k){return caches.delete(k)}));
  }).then(function(){return self.clients.claim()}));
});
self.addEventListener("fetch",function(e){
  var url=new URL(e.request.url);
  if(url.pathname.indexOf("data.json")>-1){
    e.respondWith(fetch(e.request).then(function(r){
      var cp=r.clone();caches.open(CACHE).then(function(c){c.put(e.request,cp)});return r;
    }).catch(function(){return caches.match(e.request)}));
    return;
  }
  e.respondWith(caches.match(e.request).then(function(m){return m||fetch(e.request)}));
});
