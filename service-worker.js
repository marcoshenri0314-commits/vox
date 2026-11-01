const CACHE_NAME = "vox-cache-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request).catch(() => {
      return new Response(
        "Você está sem conexão. Verifique sua internet e tente novamente.",
        {
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        }
      );
    })
  );
});
