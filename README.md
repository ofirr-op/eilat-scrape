# scrape

Find Club Hotel Eilat prices for 2, 3 and 4 nights, each board basis, and one or two rooms. Two parties are configured (`2a3c` and `4a1c`), and each party is scraped twice: the public rate (`promo=none`) and the Hot consumer-club code (`promo=mhot`).

## GitHub Actions / הרצה ב-GitHub Actions

This repo runs itself on GitHub Actions (`.github/workflows/scrape.yml`). No extra secrets: the workflow uses `GITHUB_TOKEN` only. Each grid is its own job, so a full day stays inside the per-job time limit. A last job merges the finished files and pushes them to `main`.

**Schedule.** The primary cron is `17 5 * * *` UTC: **07:17 Israel Standard Time** (winter, UTC+2), and **08:17** during Israel Daylight Time (summer, UTC+3). The minute is not 0, because GitHub often drops a schedule that fires at the top of the hour. If that run did not succeed, two backups try later the same day: `43 8 * * *` UTC (**10:43** winter / **11:43** summer) and `29 11 * * *` UTC (**13:29** winter / **14:29** summer). A backup does not scrape when a run on `main` already succeeded, or is still queued or running, on today's Israel date. A manual run always scrapes. GitHub cron is UTC only and does not move with daylight saving time.

**Run one scan by hand.** Open the **Actions** tab, choose **Scrape Club Hotel Eilat**, click **Run workflow**, leave the branch on `main`, and pick a **grid**:

| Grid | Party | Promo | Results |
| --- | --- | --- | --- |
| `2a3c` | 2 adults + 3 children (ages 4, 8, 12) | none | `output/eilat/` |
| `2a3c-mhot` | same party | `mhot` | `output/eilat/promo-mhot/` |
| `4a1c` | 4 adults + 1 child (age 8) | none | `output/eilat/party-4a1c/` |
| `4a1c-mhot` | same party | `mhot` | `output/eilat/party-4a1c/promo-mhot/` |
| `all` | both parties | both | all four directories above |

Each directory receives `results.csv`, `results.json`, `offers.csv`, and `report.html`. One gzipped history snapshot per grid is added under `output/history/runs/`.

המאגר מריץ את עצמו ב-GitHub Actions (`.github/workflows/scrape.yml`). אין סודות נוספים: ה-workflow משתמש רק ב-`GITHUB_TOKEN`. כל רשת רצה כ-job נפרד, ועבודה אחרונה מאחדת את הקבצים ודוחפת אותם ל-`main`.

**לוח זמנים.** ה-cron הראשי הוא `17 5 * * *` לפי UTC: **07:17** שעון ישראל בחורף (UTC+2), ו־**08:17** בשעון קיץ (UTC+3). הדקה אינה 0, כי GitHub לפעמים מדלג על תזמון שנופל בדיוק בראש השעה. אם הריצה הזו לא הצליחה, יש שני גיבויים באותו יום: `43 8 * * *` UTC (**10:43** בחורף / **11:43** בקיץ) ו־`29 11 * * *` UTC (**13:29** בחורף / **14:29** בקיץ). גיבוי לא סורק אם ב־`main` כבר יש ריצה שהצליחה, או שהיא עדיין בתור או רצה, לפי התאריך של היום בשעון ישראל. הרצה ידנית תמיד סורקת. ה-cron של GitHub הוא UTC בלבד ולא זז עם שעון הקיץ.

**הרצה ידנית של סריקה אחת.** נכנסים ללשונית **Actions**, בוחרים **Scrape Club Hotel Eilat**, לוחצים **Run workflow**, משאירים את הענף על `main`, ובוחרים **grid**:

| בחירה | הרכב | מבצע | איפה התוצאות |
| --- | --- | --- | --- |
| `2a3c` | 2 מבוגרים + 3 ילדים (גילאי 4, 8, 12) | בלי קוד | `output/eilat/` |
| `2a3c-mhot` | אותו הרכב | `mhot` | `output/eilat/promo-mhot/` |
| `4a1c` | 4 מבוגרים + ילד אחד (גיל 8) | בלי קוד | `output/eilat/party-4a1c/` |
| `4a1c-mhot` | אותו הרכב | `mhot` | `output/eilat/party-4a1c/promo-mhot/` |
| `all` | שני ההרכבים | שניהם | כל ארבע התיקיות |

בכל תיקייה נשמרים `results.csv`, `results.json`, `offers.csv` ו-`report.html`. צילום היסטוריה אחד לכל רשת (`*.csv.gz`) נוסף תחת `output/history/runs/`.

## Price page / עמוד המחירים

The same workflow publishes a Hebrew, phone-first page at <https://ofirr-op.github.io/eilat-scrape/>. After the results are committed it builds `site/` from `output/history/runs/*.csv.gz` and the current result files, then deploys with GitHub Pages. At the start of a run it commits `output/status.json` (`running`, with `started_at` and the grids in this run) so the page can show that a scan is in progress. A failed grid keeps the error text from the scraper log.

GitHub Pages has to be switched on once: **Settings → Pages → Build and deployment → Source: GitHub Actions**. The workflow token cannot flip that setting.

אותו workflow מפרסם עמוד בעברית, מותאם לטלפון, בכתובת <https://ofirr-op.github.io/eilat-scrape/>. אחרי שהתוצאות נשמרות הוא בונה את `site/` מ־`output/history/runs/*.csv.gz` ומקבצי התוצאות, ומפרסם ל־GitHub Pages. בתחילת ריצה נשמר `output/status.json` (מצב `running`, עם `started_at` והרשתות של הריצה) כדי שהעמוד יראה שסריקה רצה. רשת שנכשלה שומרת את טקסט השגיאה מהלוג.

צריך להפעיל את GitHub Pages פעם אחת: **Settings → Pages → Build and deployment → Source: GitHub Actions**. הטוקן של ה-workflow לא יכול לשנות את ההגדרה הזו.

The marketing page at <https://m.clubhotels.co.il/club-hotel-eilat?r=1> does not contain prices. Its booking widget (`Scripts/EngineScriptsV2/BE_Engine.min.js`) submits a search to the ASP.NET page the engine calls **RoomsPage**:

```
https://m.clubhotels.co.il/BE_Rooms.aspx
  ?lang=heb
  &hotel=1_1
  &in=YYYY-MM-DD
  &out=YYYY-MM-DD
  &rooms=1
  &ad1=2
  &ch1=3
  &inf1=0
```

Two rooms use the same page with one occupancy per room. The widget builds that as `adN`, `chN`, and `infN` for room N:

```
&rooms=2&ad1=1&ch1=2&inf1=0&ad2=1&ch2=1&inf2=0
```

`hotel=1_1` is Club Hotel Eilat (`OptimaResortID` 1, wing 1). The page is server-rendered. Each bookable rate is a `roomData` JSON attribute on a `.matrix-button` (room type, board, package name, total price, currency). There is no separate public JSON price API. `BE_EngineService.asmx/getAvalibility` feeds the date picker: one POST returns which days exist (`IsAvail`, `MinDays`, `CloseToArrival`, `CloseToDeparture`) and no prices. This tool reads prices from `BE_Rooms.aspx`, and by default uses that calendar only to skip closed check-ins.

A Hot consumer-club search is the same URL plus `&promocode=mhot`. That is a separate page, not a discount applied afterwards. On a manual check the code made rates labelled `מבצע לעד 4 לילות` exactly 7% cheaper and renamed them `… – לחברי מועדון צרכנות הוט`, left list-price rates (`לפני מבצעים`) unchanged, and on some dates (including 2026-12-15) removed the cheapest suite (`סוויטה דלקס, 2 חדרים, מטבחון`). The with-code total can therefore be higher. This tool stores both scrapes. It does not multiply by 0.93.

A date with no fitting room comes back as an empty room list plus `.no-results-text` (minimum nights, or the party does not fit one room). Those stays are recorded as `unavailable` and skipped in the cheapest-price summary.

## Board basis

Each `roomData` object has its own `MealPlan` and a stay `Price`. These are separate rates, not add-ons. `SpecialServices` was null on every rate captured from the live site, so there is no per-person half-board supplement to add on top of another plan.

| `board` | Hebrew `MealPlan` | English |
| --- | --- | --- |
| `RO` | לינה בלבד | room only |
| `BB` | כולל ארוחת בוקר | bed and breakfast |
| `HB` | חצי פנסיון | half board |

The raw half-board label sometimes has a trailing space. It is stripped before the code is assigned. Room only and breakfast are offered together. Half board is offered on fewer room types, and a stay with no half-board rate is a row with `board=HB` and `status=unavailable`.

## Two rooms

`--rooms` accepts `1`, `2`, or `1,2` (the default).

For two rooms the engine does not take "5 guests, 2 rooms". It takes a per-room occupancy. Hotel terms require a parent with any child, and the booking widget will not offer 0 adults on the second room, so every split puts **at least one adult in each room**. Ages are still not sent; only the counts are.

For the default party (2 adults, 3 children, 0 infants) the two unique splits are:

1. Room 1: 1 adult + 2 children. Room 2: 1 adult + 1 child.
2. Room 1: 1 adult + 3 children. Room 2: 1 adult + 0 children.

Swapping the rooms is the same search, so it is not requested twice. A child-only room is not searched. For each board the cheaper split that the engine actually returns is the one stored on the row. Its `split` object records the occupancies, and `booking_url` is the `BE_Rooms.aspx` link for that split (with `&promocode=mhot` only when the row's promo is `mhot`).

For **4 adults + 1 child** the two-room search is the same rule. The documented even split, which is one of the requests, is:

1. Room 1: 2 adults + 1 child (`ad1=2&ch1=1&inf1=0`). Room 2: 2 adults (`ad2=2&ch2=0&inf2=0`).

The other legal splits are also requested, and the cheaper one that comes back is stored:

2. Room 1: 3 adults + 1 child. Room 2: 1 adult.
3. Room 1: 1 adult + 1 child. Room 2: 3 adults.

The two room totals are summed. `AvailableRooms` on the page is a map of room code to remaining units. The same code is used for both rooms only when at least two units remain. `price_per_night` is the combined total divided by nights, not a per-room rate.

## Parties

`--party` accepts `2a3c`, `4a1c`, or a comma-separated list. Repeat the flag to pass both (`--party 2a3c --party 4a1c`). Omitting `--party`, or naming both, runs every configured party.

| `party` | Who | One room | Output directory |
| --- | --- | --- | --- |
| `2a3c` | 2 adults + children aged 4, 8 and 12 | `ad1=2&ch1=3&inf1=0` | `output/eilat/` when promo is `none` |
| `4a1c` | 4 adults + one child aged 8 | `ad1=4&ch1=1&inf1=0` | `output/eilat/party-4a1c/` when promo is `none` |

Child ages still go through the same brackets as before. The engine does not take each child's age. It prices three counts: adults, children, and infants. Ages are used only to build those counts.

## Party of five

`2a3c` search: **2 adults + children aged 4, 8 and 12**, for **1 room and for 2 rooms**.

The engine does not take each child's age. It prices three counts: adults, children, and infants. Ages are used only to build those counts.

Hotel terms (and the Hebrew booking copy):

- Infant: under 2
- Child: from 2 through 12
- The English widget labels adults as "from 12" and children as "up to age 12", so a 12-year-old is ambiguous

Default `--adult-from-age 13` keeps age 12 as a child, so the query is `ad1=2&ch1=3&inf1=0`. To follow the English widget instead:

```bash
python -m scrape --adult-from-age 12
```

That reclassifies age 12 as an adult (`ad1=3&ch1=2`). Ages under `--infant-under-age` (default 2) are sent as `inf1`.

The engine omits room types that cannot hold that room's occupancy. i-club member rates (`clubdeal`, `clubpricecode`) need a login, so they are excluded unless you pass `--include-club`.

`4a1c` uses the same brackets. Age 8 stays a child, so one room is `ad1=4&ch1=1&inf1=0`. Whether that occupancy fits a single room is whatever the engine returns: a date with no fitting room is `unavailable`, the same as `2a3c`.

## Promo

`--promo` accepts `none`, `mhot`, or both. Omitting it scrapes both.

| `promo` | Request | Where it is written, for party `2a3c` | For party `4a1c` |
| --- | --- | --- | --- |
| `none` | no `promocode` parameter | `output/eilat/` | `output/eilat/party-4a1c/` |
| `mhot` | `&promocode=mhot` | `output/eilat/promo-mhot/` | `output/eilat/party-4a1c/promo-mhot/` |

Each directory has `results.csv`, `results.json`, `offers.csv`, and `report.html`. A row's `booking_url` and `url` are the URL that was fetched for that promo. `promo=none` URLs do not contain `promocode`. `promo=mhot` URLs end with `&promocode=mhot`.

The daily command scrapes all four combinations. `2a3c` / `none` stays in `output/eilat/` so older paths keep working. The other three are sibling directories, not extra rows mixed into that file.

## Nights

`--nights` is the number of **nights** (check-out minus check-in). The default is `2,3,4`, and every result row has a `nights` field.

A stay people call "4 days" is often 3 nights (arrive Friday, leave Monday). Passing `--nights 2,3` keeps only those lengths.

## Setup

Python 3.11 or newer. No third-party packages.

```bash
python -m scrape --help
```

Optional install, so the `scrape` command is on `PATH`:

```bash
pip install -e .
```

## Usage

Full window: every check-in from tomorrow through 6 months, nights 2, 3 and 4, rooms 1 and 2, both parties, both promos. `2a3c` is 9 requests per date per promo (one room, plus two adult splits for two rooms, times three lengths). `4a1c` is 12 (one room, plus three adult splits for two rooms, times three lengths). Both promos are 42 `BE_Rooms.aspx` requests per check-in date before the calendar pre-check.

```bash
python3 -m scrape --output output/eilat --history output/history --refresh
```

That command is the daily routine. It writes four grids and four history snapshots. `--history` defaults to `output/history`, so the command records the run on its own. `--refresh` ignores the 24-hour response cache. Omit `--party` and `--promo` to scrape every combination. A single grid is `--party 4a1c --promo mhot` (or `--promo none`). A short sample does not belong in that history:

```bash
python -m scrape --max-dates 4 --output output/sample --no-history
```

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--months` | `6` | Check-in from tomorrow through this many months, inclusive |
| `--nights` | `2,3,4` | Stay lengths in nights |
| `--rooms` | `1,2` | Room counts. `2` splits the party so each room has an adult |
| `--party` | `2a3c,4a1c` | `2a3c` and/or `4a1c`. Omit it, or pass both, to run every party |
| `--promo` | `none,mhot` | `none` has no promocode. `mhot` is a separate scrape with `promocode=mhot`. Omit it to run both |
| `--adults` | party preset | Override the adult count for a single `--party` |
| `--children-ages` | party preset | Override ages for a single `--party`. `2a3c` is `4,8,12`. `4a1c` is `8` |
| `--adult-from-age` | `13` | Listed age that is priced as an adult |
| `--infant-under-age` | `2` | Listed age priced as an infant |
| `--output` | `output/eilat` | Base directory. `2a3c`/`none` is written here. Other combos go under `party-*` and `promo-*` |
| `--history` | `output/history` | Append one gzipped CSV per party × promo under `runs/` |
| `--no-history` | off | Skip the history append (use this for samples) |
| `--hotel` | `1_1` | Engine hotel id |
| `--delay` | `1.5` | Pause between uncached requests, plus a little jitter |
| `--retries` | `4` | Retries on timeouts and HTTP 429/5xx |
| `--cache-dir` | `.cache` | Disk cache of response bodies |
| `--cache-hours` | `24` | How long a cached response is reused |
| `--refresh` | off | Ignore the cache |
| `--max-dates` | `0` (every day) | Evenly sample this many check-in dates |
| `--include-club` | off | Let member-only rates win |
| `--transport` | `auto` | `direct`, `reader`, or `auto` |
| `--no-avail-precheck` | off (pre-check on) | Crawl every check-in. The default POSTs `getAvalibility` once and skips closed dates |

## Result format (schema 3)

`results.json` has `schema_version: 3`. One object in `results` is one combination of **check-in × nights × board × rooms** for that file's party and promo. The same columns are in `results.csv`. Fields that existed in schema 1 (`check_in`, `check_out`, `nights`, `board_he`, `board_en`, `status`, `hotel_name`, `room_type`, `package_name`, `total_price`, `price_per_night`, `currency`, `currency_symbol`, `room_code`, `price_code_type`, `requires_club`, `offers_count`, `adults`, `children`, `infants`, `children_ages`, `reason`, `url`, `cheapest`, `offers`) are still there, and schema 2's `rooms`, `board`, `booking_url`, and `split` are still there. `total_price` on the row is the whole booking (both rooms when `rooms` is 2). `cheapest.total_price` matches it. `cheapest.components` is the per-room rate or rates that were summed.

`party` is `2a3c` or `4a1c`. `promo` is `none` or `mhot`. A file written before those columns (the in-progress `output/eilat/partial/` slice, and history snapshots from 24–26 Oct) omits them; readers treat a missing `party` as `2a3c` and a missing `promo` as `none`. The finished `output/eilat/` grid from the 2026-10-26 07:17Z run was stamped with those columns. Its prices and booking URLs were not recomputed, and its URLs still have no promocode.

| Field | Meaning |
| --- | --- |
| `nights` | 2, 3, or 4 |
| `rooms` | 1 or 2 |
| `party` | `2a3c` or `4a1c`. Missing means `2a3c` |
| `promo` | `none` or `mhot`. Missing means `none` |
| `board` | `RO`, `BB`, or `HB` |
| `board_he` / `board_en` | Hebrew label and English label |
| `total_price` | Stay total in `currency` (ILS). Null when `status` is not `available` |
| `price_per_night` | `total_price / nights` for the whole booking |
| `booking_url` | `BE_Rooms.aspx` link with the dates, room count, and per-room occupancy. Same value as `url`. Includes `&promocode=mhot` only when `promo` is `mhot` |
| `split` | `{label, rooms: [{room, adults, children, infants}, ...]}` for the split that won. Null when nothing was bookable |
| `room_type` | One name, or both names joined with ` + ` |
| `status` | `available` or `unavailable` |
| `offers` | Every public rate of this board on the winning page. `selected` marks the rate or rates in the total |

`offers.csv` is one row per rate in those `offers` arrays, with `nights`, `rooms`, `board`, `room_number`, `party`, `promo`, and `is_cheapest` (true when `selected` is true).

`summary.cheapest_by_combination` is keyed `"{nights}|{board}|{rooms}"` (for example `3|HB|2`) and holds the cheapest available row for that cell, without the offers array. `summary.cheapest_by_nights` is the cheapest row of any board and room count for that length. `summary.cheapest_overall` is the 15 lowest totals.

`report.html` repeats the combination table and the full grid.

Prices are the engine's stay total in shekels (`₪`, code `ILS`).

## Politeness and cache

Uncached requests wait `--delay` seconds (default 1.5) plus a short random jitter. Timeouts, a body that ends early (`IncompleteRead`), and HTTP 429/500/502/503/504 are retried with exponential backoff. Successful HTML is stored under `--cache-dir` for `--cache-hours` (default 24), keyed by the booking URL, so a second run inside that window does not hit the site again. Pass `--refresh` to force new requests.

Before the rooms crawl, the default is one POST to `https://m.clubhotels.co.il/BE_EngineService.asmx/getAvalibility` (`Content-Type: application/json; charset=utf-8`, `Referer` and `Origin` `https://m.clubhotels.co.il`, body `hotelID` `1`, `wing` null, `dsn` `""`, `lang` `heb`, `days` 550). Each row's `DayDate` is an ASP.NET `/Date(milliseconds)/` value. A check-in with `IsAvail` false or `CloseToArrival` true is written as `unavailable` for every nights × board × rooms cell, with `reason` beginning `calendar:` and no `BE_Rooms.aspx` request. Its `booking_url` is the first split that would have been fetched, with `&promocode=mhot` only when `promo` is `mhot`. Check-ins after the last calendar day are left out of the crawl and out of the output. `MinDays` and `CloseToDeparture` are not used as skip rules. If the POST fails or the body is not a calendar, nothing is printed and every date in the window is fetched as before. `--no-avail-precheck` skips the POST.

On 2026-10-26 that calendar was 139 days, 2026-10-26 through 2027-03-13 (23 of them `IsAvail` false, `CloseToArrival` false on every row, `MinDays` 1 on every row). The six-month window was 183 check-ins, 2026-10-27 through 2027-04-27. 23 of those were closed and 45 were after 2027-03-13. Both sets had no available price in the finished grids. A four-grid run is 42 rooms requests per check-in, so skipping those 68 dates removes 2,856 of 7,686 requests (about 37%), plus the one calendar POST. The run still fetches dates the calendar calls open when the party or the stay length does not fit.

On 2026-10-27 the calendar was 138 days through 2027-03-13. The six-month window was 183 check-ins, 2026-10-28 through 2027-04-28. 23 were closed and 46 were after 2027-03-13, so the crawl fetched 114 open dates (4,788 rooms requests instead of 7,686). The closed dates are in each grid as `unavailable`. The 46 later dates are not in the grids, which is why each snapshot is 2,466 rows. On every check-in that was also in the 2026-10-26 grids, status, total, and room type matched.

On 2026-10-28 the calendar was 137 days through 2027-03-13. The six-month window was 183 check-ins, 2026-10-29 through 2027-04-29. 22 were closed and 47 were after 2027-03-13, so the crawl fetched 114 open dates (4,788 rooms requests instead of 7,686). The closed dates are in each grid as `unavailable`. The 47 later dates are not in the grids, which is why each snapshot is 2,448 rows. On every check-in that was also in the 2026-10-27 grids, status, total, and room type matched.

Unavailable dates stay in the CSV and JSON with `status=unavailable`. They are not treated as errors.

## Cloudflare

The rooms page is a normal GET. No login and no browser are required when the request is allowed.

Cloudflare in front of `m.clubhotels.co.il` does not treat every client the same:

- This tool's client (`urllib`, a mobile Safari `User-Agent`, an HTML `Accept`, Hebrew `Accept-Language`, and a referer of the hotel page) received HTTP 200 from `BE_Rooms.aspx` on the live runs.
- `curl` and headless Chrome from the same network, including `curl` with those same headers, received an immediate **"Sorry, you have been blocked"** page. That is a hard block, not a JavaScript challenge, so waiting does not clear it. Static files (`/Scripts/EngineScriptsV2/BE_Engine.min.js`, `robots.txt`) still return 200.

`--transport auto` (the default) tries the booking site directly. If that response is the Cloudflare block page, the rest of the run fetches the **same** `BE_Rooms.aspx` URL through `https://r.jina.ai/` with `X-Return-Format: html`, and says so once on stdout. Use `--transport direct` to refuse that fallback. Use `--transport reader` only when you already know direct access is blocked.

## Price history

Every scrape appends one file per party × promo. Nothing already in the store is rewritten.

```
output/history/runs/<UTC timestamp>.csv.gz                  2a3c, promo none
output/history/runs/<UTC timestamp>-mhot.csv.gz             2a3c, promo mhot
output/history/runs/<UTC timestamp>-4a1c.csv.gz             4a1c, promo none
output/history/runs/<UTC timestamp>-4a1c-mhot.csv.gz        4a1c, promo mhot
```

The timestamp is `generated_at` in UTC, with colons removed so the name is safe on every filesystem: `2026-10-25T070911.684574Z.csv.gz`. Inside the file, `scraped_at` keeps the colons and a `Z` suffix (`2026-10-25T07:09:11.684574Z`). One row is one check-in × nights × board × rooms cell for that file's party and promo. Available and unavailable rows are both kept. The file has no offer list. A non-default party or promo adds the suffix above. `2a3c` with `promo=none` keeps the original filename.

| Column | Meaning |
| --- | --- |
| `scraped_at` | When that scrape finished, ISO-8601 UTC |
| `check_in` | Stay check-in, `YYYY-MM-DD` |
| `nights` | 2, 3, or 4 |
| `rooms` | 1 or 2 |
| `board` | `RO`, `BB`, or `HB` |
| `status` | `available` or `unavailable` |
| `total_price` | Stay total in ILS, two decimals. Empty when unavailable |
| `price_per_night` | `total_price / nights` for the whole booking. Empty when unavailable |
| `room_type` | Winning room name, or both names joined with ` + `. Empty when unavailable |
| `party` | `2a3c` or `4a1c`. Snapshots from before this column are read as `2a3c` |
| `promo` | `none` or `mhot`. Snapshots from before this column are read as `none` |

A check-in that has rolled out of the six-month window has no later row. That is the window moving, not a sold-out night. Compare `status` on the rows that were actually scraped.

Five finished `2a3c` / `none` grids are stored. The first three have no `party` or `promo` column; both are read as the defaults. The 2026-10-27 and 2026-10-28 files have those columns. Each timestamp is `generated_at` from that run's `results.json` (the moment the scrape wrote the file). Commit time was a few minutes later and was not used. The files are left byte-for-byte as they were written.

| File | Rows | Bytes | Source |
| --- | --- | --- | --- |
| `output/history/runs/2026-10-24T074751.745627Z.csv.gz` | 3,294 | 21,687 | `a9fa688`, `generated_at` 2026-10-24T07:47:51.745627Z |
| `output/history/runs/2026-10-25T070911.684574Z.csv.gz` | 3,294 | 21,589 | `b9e9563`, `generated_at` 2026-10-25T07:09:11.684574Z |
| `output/history/runs/2026-10-26T071755.741993Z.csv.gz` | 3,294 | 22,219 | `b88ed72`, `generated_at` 2026-10-26T07:17:55.741993Z |
| `output/history/runs/2026-10-26T150422.228713Z-4a1c.csv.gz` | 3,294 | 22,588 | `4a1c` / `none`, `generated_at` 2026-10-26T15:04:22.228713Z |
| `output/history/runs/2026-10-26T161414.805063Z-4a1c-mhot.csv.gz` | 3,294 | 23,788 | `4a1c` / `mhot`, `generated_at` 2026-10-26T16:14:14.805063Z |
| `output/history/runs/2026-10-26T170623.969737Z-mhot.csv.gz` | 3,294 | 23,772 | `2a3c` / `mhot`, `generated_at` 2026-10-26T17:06:23.969737Z |
| `output/history/runs/2026-10-27T064106.799861Z.csv.gz` | 2,466 | 19,905 | `2a3c` / `none`, `79396a3`, `generated_at` 2026-10-27T06:41:06.799861Z |
| `output/history/runs/2026-10-27T071701.470516Z-mhot.csv.gz` | 2,466 | 21,106 | `2a3c` / `mhot`, `8cba519`, `generated_at` 2026-10-27T07:17:01.470516Z |
| `output/history/runs/2026-10-27T080216.035791Z-4a1c.csv.gz` | 2,466 | 19,907 | `4a1c` / `none`, `17b277f`, `generated_at` 2026-10-27T08:02:16.035791Z |
| `output/history/runs/2026-10-27T085031.680987Z-4a1c-mhot.csv.gz` | 2,466 | 21,114 | `4a1c` / `mhot`, `a6c5555`, `generated_at` 2026-10-27T08:50:31.680987Z |
| `output/history/runs/2026-10-28T065606.202971Z.csv.gz` | 2,448 | 19,848 | `2a3c` / `none`, `175daaf`, `generated_at` 2026-10-28T06:56:06.202971Z |
| `output/history/runs/2026-10-28T075151.466994Z-mhot.csv.gz` | 2,448 | 21,041 | `2a3c` / `mhot`, `0bdac69`, `generated_at` 2026-10-28T07:51:51.466994Z |
| `output/history/runs/2026-10-28T091233.531226Z-4a1c.csv.gz` | 2,448 | 19,851 | `4a1c` / `none`, `a767171`, `generated_at` 2026-10-28T09:12:33.531226Z |
| `output/history/runs/2026-10-28T114822.250961Z-4a1c-mhot.csv.gz` | 2,448 | 21,059 | `4a1c` / `mhot`, `a7fa698`, `generated_at` 2026-10-28T11:48:22.250961Z |

The first three run files are 65,495 bytes and have no `party` or `promo` column. `output/eilat/partial/` is the in-progress slice of the 2026-10-24 run, so it is not a separate history file. `output/eilat/partial/party-4a1c-promo-none.csv` is a later log slice of the 4a1c public scrape, not a history snapshot.

Query one stay. The lines are oldest scrape first. When several scrapes share the lowest total, the earliest of them is the cheapest time to book:

```bash
python3 -m scrape.history_query --check-in 2026-11-14 --nights 2 --board RO --rooms 1
python3 -m scrape.history_query --check-in 2026-11-14 --nights 2 --board RO --rooms 1 --party 4a1c --promo mhot
```

`--party` defaults to `2a3c` and `--promo` defaults to `none`, so the command above still reads the original public-rate series. A snapshot with no `party` or `promo` column matches that default and does not match `4a1c` or `mhot`.

```
Stay 2026-11-14, 2 nights, RO, 1 room, party 2a3c, promo none
observations=5

scraped_at                        status         total_price   price_per_night  room_type
2026-10-24T07:47:51.745627Z       available          1647.06            823.53  סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר
2026-10-25T07:09:11.684574Z       available          1647.06            823.53  סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר
2026-10-26T07:17:55.741993Z       available          1647.06            823.53  סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר
2026-10-27T06:41:06.799861Z       available          1647.06            823.53  סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר
2026-10-28T06:56:06.202971Z       available          1647.06            823.53  סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר

Cheapest to book: 1647.06 ILS (823.53/night), first seen 2026-10-24T07:47:51.745627Z
Room: סוויטה דלקס, 2 חדרים, מטבחון ומרפסת - 50 מ"ר
```

`--history` defaults to `output/history`. The command exits 1 when that stay has no rows.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Live results

### 2a3c / none

Refetched with `--refresh` on 2026-10-28 (0 errors, no cache hits). Check-ins in the file are **2026-10-29 through 2027-03-13** (136 dates). The six-month window runs through 2027-04-29; 47 dates after the calendar's last day are omitted. Nights 2/3/4, rooms 1 and 2, boards RO, BB, and HB. Party `2a3c`: 2 adults and 3 children aged 4, 8, and 12. Promo `none` (booking URLs have no promocode). 2,448 rows: 1,574 available, 874 unavailable. `started_at` `2026-10-28T06:04:35.429320Z`. `generated_at` `2026-10-28T06:56:06.202971Z`. Files are `output/eilat/results.json` and `results.csv`. History: `output/history/runs/2026-10-28T065606.202971Z.csv.gz` (`175daaf`). Every cell that was also in the 2026-10-27 grid has the same status, total, and room type. `output/eilat/partial/` is the earlier snapshot through 2027-03-07 and still has no party or promo column (read those rows as `2a3c` / `none`).

Half board is a real separate rate (`board=HB`, `board_he` חצי פנסיון) on 374 of the 816 HB rows. The other HB rows are unavailable because that plan was not offered, or the whole stay was unavailable. It is not a per-person add-on.

Cheapest total in each nights × board × rooms cell:

| Nights | Board | Rooms | Total (ILS) | Per night | Check-in | Room |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | RO | 1 | 1,579.16 | 789.58 | 2026-12-15 | סוויטה דלקס |
| 2 | BB | 1 | 2,161.16 | 1,080.58 | 2026-12-15 | סוויטה דלקס |
| 2 | HB | 1 | 3,567.66 | 1,783.83 | 2026-12-15 | סוויטה דלקס |
| 2 | RO | 2 | 2,382.32 | 1,191.16 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 2 | BB | 2 | 2,964.32 | 1,482.16 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 2 | HB | 2 | 4,370.82 | 2,185.41 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 3 | RO | 1 | 2,509.39 | 836.46 | 2026-12-14 | סוויטה דלקס |
| 3 | BB | 1 | 3,382.39 | 1,127.46 | 2026-12-14 | סוויטה דלקס |
| 3 | HB | 1 | 5,492.14 | 1,830.71 | 2026-12-14 | סוויטה דלקס |
| 3 | RO | 2 | 3,621.98 | 1,207.33 | 2027-01-09 | קומפורט + סטנדרט |
| 3 | BB | 2 | 4,494.98 | 1,498.33 | 2027-01-09 | קומפורט + סטנדרט |
| 3 | HB | 2 | 6,701.73 | 2,233.91 | 2027-01-10 | קומפורט + סטנדרט |
| 4 | RO | 1 | 3,294.12 | 823.53 | 2026-12-12 | סוויטה דלקס |
| 4 | BB | 1 | 4,458.12 | 1,114.53 | 2026-12-12 | סוויטה דלקס |
| 4 | HB | 1 | 7,406.92 | 1,851.73 | 2026-12-13 | סוויטה דלקס |
| 4 | RO | 2 | 4,881.04 | 1,220.26 | 2027-01-09 | קומפורט + סטנדרט |
| 4 | BB | 2 | 6,045.04 | 1,511.26 | 2027-01-09 | קומפורט + סטנדרט |
| 4 | HB | 2 | 8,974.44 | 2,243.61 | 2027-01-10 | קומפורט + סטנדרט |

Every available two-room row used the split “1 adult + 2 children” and “1 adult + 1 child”. The “1 adult + 3 children” plus “1 adult alone” split was priced and was never cheaper. Dates the engine rejects (minimum nights, or the party does not fit) are `status=unavailable` with the site’s Hebrew message. Prices move, so re-run for a current quote. Cached responses are reused for 24 hours.

### 4a1c / none

Fetched with `--refresh` on 2026-10-28. Check-ins in the file are **2026-10-29 through 2027-03-13** (136 dates; 47 dates after the calendar are omitted). Nights 2/3/4, rooms 1 and 2, boards RO, BB, and HB. Party `4a1c`: 4 adults and one child aged 8. Promo `none`. 2,448 rows: 1,574 available, 874 unavailable, 0 errors. `started_at` `2026-10-28T07:51:52.303248Z`. `generated_at` `2026-10-28T09:12:33.531226Z`. Files are `output/eilat/party-4a1c/`. History: `output/history/runs/2026-10-28T091233.531226Z-4a1c.csv.gz` (`a767171`). Every cell that was also in the 2026-10-27 grid has the same status, total, and room type.

One room holds this party: 300 dates had a public RO rate and 300 had BB; 187 had HB. The one-room page offers the deluxe suite with a kitchenette, junior deluxe, executive, master, and Caribbean suites. It does not offer the family deluxe, standard deluxe, or comfort deluxe. Those three appear on the two-room pages.

Three two-room splits were requested. The documented even split is room 1 = 2 adults + the child (`ad1=2&ch1=1&inf1=0`) and room 2 = 2 adults (`ad2=2&ch2=0&inf2=0`). Every available two-room row stored the other uneven split instead: “1 adult + 1 child” and “3 adults” (`ad1=1&ch1=1&inf1=0&ad2=3&ch2=0&inf2=0`). The even split and the “3 adults + 1 child / 1 adult” split were priced and were never strictly cheaper. On the family-suite dates the “3 adults + 1 child” page is the one that puts that room in the room-only log line; it still loses to the 1+3 adult split.

Cheapest totals match the `2a3c` / `none` table above on price and check-in for every cell. The 3-night and 4-night two-room winners name the same two room types with standard before comfort.

| Nights | Board | Rooms | Total (ILS) | Per night | Check-in | Room |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | RO | 1 | 1,579.16 | 789.58 | 2026-12-15 | סוויטה דלקס |
| 2 | BB | 1 | 2,161.16 | 1,080.58 | 2026-12-15 | סוויטה דלקס |
| 2 | HB | 1 | 3,567.66 | 1,783.83 | 2026-12-15 | סוויטה דלקס |
| 2 | RO | 2 | 2,382.32 | 1,191.16 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 2 | BB | 2 | 2,964.32 | 1,482.16 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 2 | HB | 2 | 4,370.82 | 2,185.41 | 2026-12-15 | סוויטה דלקס + סוויטה דלקס |
| 3 | RO | 1 | 2,509.39 | 836.46 | 2026-12-14 | סוויטה דלקס |
| 3 | BB | 1 | 3,382.39 | 1,127.46 | 2026-12-14 | סוויטה דלקס |
| 3 | HB | 1 | 5,492.14 | 1,830.71 | 2026-12-14 | סוויטה דלקס |
| 3 | RO | 2 | 3,621.98 | 1,207.33 | 2027-01-09 | סטנדרט + קומפורט |
| 3 | BB | 2 | 4,494.98 | 1,498.33 | 2027-01-09 | סטנדרט + קומפורט |
| 3 | HB | 2 | 6,701.73 | 2,233.91 | 2027-01-10 | סטנדרט + קומפורט |
| 4 | RO | 1 | 3,294.12 | 823.53 | 2026-12-12 | סוויטה דלקס |
| 4 | BB | 1 | 4,458.12 | 1,114.53 | 2026-12-12 | סוויטה דלקס |
| 4 | HB | 1 | 7,406.92 | 1,851.73 | 2026-12-13 | סוויטה דלקס |
| 4 | RO | 2 | 4,881.04 | 1,220.26 | 2027-01-09 | סטנדרט + קומפורט |
| 4 | BB | 2 | 6,045.04 | 1,511.26 | 2027-01-09 | סטנדרט + קומפורט |
| 4 | HB | 2 | 8,974.44 | 2,243.61 | 2027-01-10 | סטנדרט + קומפורט |

Booking URL for the 2-night room-only one-room cell (no promocode):

`https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1&in=2026-12-15&out=2026-12-17&rooms=1&ad1=4&ch1=1&inf1=0`

### 4a1c / mhot

Same window, fetched with `promocode=mhot` on every request. 2,448 rows: 1,574 available, 874 unavailable, 0 errors. `started_at` `2026-10-28T09:12:34.285485Z`. `generated_at` `2026-10-28T11:48:22.250961Z`. Files are `output/eilat/party-4a1c/promo-mhot/`. History: `output/history/runs/2026-10-28T114822.250961Z-4a1c-mhot.csv.gz` (`a7fa698`). Every `booking_url` ends with `&promocode=mhot`. Every cell that was also in the 2026-10-27 grid has the same status, total, and room type.

Where both promos had a price, the mhot total was higher on 367 rows and lower on 1,207. The code is not a flat 7% off the cheapest public room. The deluxe suite with a kitchenette drops out, so the cheapest one-room stay becomes a junior deluxe and costs more than `4a1c` / `none` (2-night RO 1,937.71 versus 1,579.16). Two rooms can go the other way (2-night RO 2,215.55 versus 2,382.32). The stored two-room split is again “1 adult + 1 child” and “3 adults” on every available row.

| Nights | Board | Rooms | Total (ILS) | Per night | Check-in | Room |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | RO | 1 | 1,937.71 | 968.86 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 2 | BB | 1 | 2,478.97 | 1,239.48 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 2 | HB | 1 | 3,832.12 | 1,916.06 | 2026-12-15 | סוויטה ג'וניור דלקס |
| 2 | RO | 2 | 2,215.55 | 1,107.78 | 2027-01-09 | סטנדרט + קומפורט |
| 2 | BB | 2 | 2,756.82 | 1,378.41 | 2027-01-09 | סטנדרט + קומפורט |
| 2 | HB | 2 | 4,137.03 | 2,068.51 | 2027-01-10 | סטנדרט + קומפורט |
| 3 | RO | 1 | 3,073.45 | 1,024.48 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 3 | BB | 1 | 3,885.34 | 1,295.11 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 3 | HB | 1 | 6,018.82 | 2,006.27 | 2027-03-06 | סוויטה ג'וניור דלקס |
| 3 | RO | 2 | 3,368.43 | 1,122.81 | 2027-01-09 | סטנדרט + קומפורט |
| 3 | BB | 2 | 4,180.34 | 1,393.45 | 2027-01-09 | סטנדרט + קומפורט |
| 3 | HB | 2 | 6,232.61 | 2,077.54 | 2027-01-10 | סטנדרט + קומפורט |
| 4 | RO | 1 | 4,218.21 | 1,054.55 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 4 | BB | 1 | 5,300.73 | 1,325.18 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 4 | HB | 1 | 8,079.22 | 2,019.81 | 2027-03-06 | סוויטה ג'וניור דלקס |
| 4 | RO | 2 | 4,539.36 | 1,134.84 | 2027-01-09 | סטנדרט + קומפורט |
| 4 | BB | 2 | 5,621.90 | 1,405.47 | 2027-01-09 | סטנדרט + קומפורט |
| 4 | HB | 2 | 8,346.23 | 2,086.56 | 2027-01-10 | סטנדרט + קומפורט |

Booking URL for the 2-night room-only one-room cell:

`https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1&in=2027-01-09&out=2027-01-11&rooms=1&ad1=4&ch1=1&inf1=0&promocode=mhot`

### 2a3c / mhot

Same window for the original party, with `promocode=mhot`. 2,448 rows: 1,574 available, 874 unavailable, 0 errors. `started_at` `2026-10-28T06:56:07.069969Z`. `generated_at` `2026-10-28T07:51:51.466994Z`. Files are `output/eilat/promo-mhot/`. History: `output/history/runs/2026-10-28T075151.466994Z-mhot.csv.gz` (`0bdac69`). Every `booking_url` ends with `&promocode=mhot`. Every cell that was also in the 2026-10-27 grid has the same status, total, and room type.

The 2026-10-26 attempt at `2026-10-26T16:14:15Z` stopped when the connection returned a short body (`IncompleteRead`). That day's completed run reused the cached pages and fetched the rest. Truncated bodies are retried. The 2026-10-28 refetch did not use the cache.

The cheapest cell in each nights × board × rooms group has the same total and check-in as `4a1c` / `mhot`. One room is again the junior deluxe. Two rooms use “1 adult + 2 children” and “1 adult + 1 child”, with comfort named before standard.

| Nights | Board | Rooms | Total (ILS) | Per night | Check-in | Room |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | RO | 1 | 1,937.71 | 968.86 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 2 | BB | 1 | 2,478.97 | 1,239.48 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 2 | HB | 1 | 3,832.12 | 1,916.06 | 2026-12-15 | סוויטה ג'וניור דלקס |
| 2 | RO | 2 | 2,215.55 | 1,107.78 | 2027-01-09 | קומפורט + סטנדרט |
| 2 | BB | 2 | 2,756.82 | 1,378.41 | 2027-01-09 | קומפורט + סטנדרט |
| 2 | HB | 2 | 4,137.03 | 2,068.51 | 2027-01-10 | קומפורט + סטנדרט |
| 3 | RO | 1 | 3,073.45 | 1,024.48 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 3 | BB | 1 | 3,885.34 | 1,295.11 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 3 | HB | 1 | 6,018.82 | 2,006.27 | 2027-03-06 | סוויטה ג'וניור דלקס |
| 3 | RO | 2 | 3,368.43 | 1,122.81 | 2027-01-09 | קומפורט + סטנדרט |
| 3 | BB | 2 | 4,180.34 | 1,393.45 | 2027-01-09 | קומפורט + סטנדרט |
| 3 | HB | 2 | 6,232.61 | 2,077.54 | 2027-01-10 | קומפורט + סטנדרט |
| 4 | RO | 1 | 4,218.21 | 1,054.55 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 4 | BB | 1 | 5,300.73 | 1,325.18 | 2027-01-09 | סוויטה ג'וניור דלקס |
| 4 | HB | 1 | 8,079.22 | 2,019.81 | 2027-03-06 | סוויטה ג'וניור דלקס |
| 4 | RO | 2 | 4,539.36 | 1,134.84 | 2027-01-09 | קומפורט + סטנדרט |
| 4 | BB | 2 | 5,621.90 | 1,405.47 | 2027-01-09 | קומפורט + סטנדרט |
| 4 | HB | 2 | 8,346.23 | 2,086.56 | 2027-01-10 | קומפורט + סטנדרט |

Booking URL for the 2-night room-only one-room cell:

`https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1&in=2027-01-09&out=2027-01-11&rooms=1&ad1=2&ch1=3&inf1=0&promocode=mhot`
