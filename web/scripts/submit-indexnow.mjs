const siteUrl = "https://telepipe.me";
const host = "telepipe.me";
const key = "2ea2aec9a95c703b90f73a028dabbb6a";

const requestedUrls = process.argv.slice(2).map((value) => new URL(value, siteUrl).href);

async function sitemapUrls() {
  const response = await fetch(`${siteUrl}/sitemap.xml`);
  if (!response.ok) {
    throw new Error(`Could not read sitemap: ${response.status} ${response.statusText}`);
  }

  const xml = await response.text();
  return [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((match) => match[1]);
}

const urlList = requestedUrls.length > 0 ? requestedUrls : await sitemapUrls();

if (urlList.length === 0) {
  throw new Error("No URLs found for IndexNow submission.");
}

const response = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "content-type": "application/json; charset=utf-8" },
  body: JSON.stringify({
    host,
    key,
    keyLocation: `${siteUrl}/${key}.txt`,
    urlList,
  }),
});

if (!response.ok) {
  throw new Error(`IndexNow rejected the submission: ${response.status} ${response.statusText}`);
}

console.log(`IndexNow accepted ${urlList.length} URL${urlList.length === 1 ? "" : "s"}.`);
