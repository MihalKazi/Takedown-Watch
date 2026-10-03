## What this record is

Takedown Watch keeps a mechanical record of what a fixed set of Bangladeshi news outlets publish online. It captures each article when it first appears, stores exactly what was served, and submits the address to the Internet Archive so that an independent copy exists outside our own systems. From the next stage of the project it will revisit each article on a fixed schedule and record, as structured events, when an article disappears or its text changes.

## How articles are found

For each outlet we look for its RSS feeds and news sitemaps: first where the outlet itself declares them (its robots.txt file and the links on its homepage), then at a few common addresses. A source is used only after it has been fetched, parsed, and shown to list recent articles from the outlet's own site. Every address we try is recorded, including those that fail.

Each run reads those sources and stores the complete list of addresses in every feed and sitemap it fetched, whether or not they are captured. Entries dated within the last 48 hours, and undated entries in feeds and news sitemaps, are queued for capture. Older entries stay in the record of the listing they appeared in.

Addresses are normalised before comparison: tracking parameters such as `utm_source` are removed, and when a page names a different canonical address, the two are recorded as one article. Nothing is deleted when two addresses turn out to be the same article.

## How pages are fetched

- The crawler identifies itself honestly, as `TakedownWatch` with a link to activaterights.org.
- It sends at most one request every two seconds to any site. The limit is enforced in software, and applies to redirects and retries too.
- It follows robots.txt, as defined in RFC 9309. If a site's robots.txt cannot be read, the whole site is treated as off-limits for that run. An address robots.txt disallows is recorded as not requested.
- Server errors and timeouts are retried with increasing delays, up to three attempts. A page reported as not found (404) or gone (410) is never retried.
- A Cloudflare challenge page is recorded as a challenge. We make no attempt to solve or bypass it, and no JavaScript is run.
- Every request is recorded with its time, result, and the network location it was made from, whether it succeeded or not.

## What is stored

Only a successful HTML response creates a snapshot. A snapshot holds the time, the response status, the final address, the headline, the byline, the publication and modification dates exactly as the page states them, the main text as extracted, and the full HTML as received. Snapshots are never edited, backfilled or deleted. Each records the version of the extraction software that produced it, so that improvements to our own software can always be told apart from changes made by an outlet.

## Bangla text

The same Bangla text can be encoded in more than one way: কো, for example, can be stored as one character or as two. Before any two texts are compared, both are normalised to a single form (Unicode NFC), with variants of spaces, quotation marks and dashes unified. Zero-width joiners inside conjuncts are kept, because they change how a word is drawn. Normalisation is used only for comparison. The stored text is exactly as extracted.

One limitation is open: the extraction software's decision about where an article's text begins can itself vary with how the page is encoded. We test for this against real articles and will not publish comparisons of text until it is resolved.

## An independent copy

Each captured page is submitted to the Internet Archive's Save Page Now service as a separate job, so capture never waits for it. The result of every submission is recorded with the archive address it produced. The archive rate shown on the overview is the share of captured pages that have at least one confirmed copy at the Internet Archive.

## Checking again (planned)

In the next stage, each article will be checked again 1 hour, 6 hours, 24 hours, 3 days, 7 days, 30 days, 90 days and 365 days after it was first captured. An article will be recorded as gone only after at least three consecutive failed checks spanning at least six hours: a single failed request never produces an event. Every change will be recorded, however small, and the article's age at the time of the change will decide the order in which people review it, never whether it is kept. This is not running yet.

## What this record says, and what it does not

The record holds observations: this address returned "not found"; this text changed; this byline became empty; here is the independent copy. It does not record why. Articles are removed or edited for many ordinary reasons, including corrections, legal requests, duplicates and site redesigns, and a mechanical record cannot tell these apart. Interpretation will only ever be added by named people, as signed annotations stored separately from the observations and reviewed before use.

## What is published, and when

At this stage the site publishes only coverage figures and this method. Nothing about any individual article's removal or change will be published until an editorial policy for doing so is in place.

Figures are published only for groups of outlets. A group with fewer than three outlets contributing captures is withheld, because a figure for one or two outlets is effectively a figure about them. The outlets monitored are the press this project exists to defend, and a figure about a single outlet could be turned against it.

## Current limitations

- Some monitored outlets have no source we can currently read: they publish no feed, block automated requests, or serve pages only after a browser check. They remain on the monitored list but contribute nothing until that changes.
- All requests are made from one network location. Differences seen only from inside or outside Bangladesh are not yet detectable.
- Articles already older than 48 hours when first found are not captured, although their addresses are kept.
