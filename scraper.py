"""
狼叔的游戏雷达 - RSS/网页抓取脚本
抓取 18 个游戏媒体源，生成日报 HTML
参照 AI HOT 输出规范
"""
import json
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
import requests

# ── Config ──
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TIMEOUT = 15
MAX_WORKERS = 12
_print_lock = threading.Lock()
_session_local = threading.local()


def get_session():
    """每个线程复用独立 Session，启用连接池"""
    if not hasattr(_session_local, "session"):
        session = requests.Session()
        session.headers.update({"User-Agent": UA})
        _session_local.session = session
    return _session_local.session
BEIJING = timezone(timedelta(hours=8))
NOW = datetime.now(BEIJING)
TODAY = NOW.strftime("%Y-%m-%d")
OUTPUT_DIR = Path(__file__).parent

# 分类标签
CATS = {
    "new-game": "新游发布/更新",
    "industry": "行业动态",
    "hardware": "硬件技术",
    "esports": "电竞赛事",
    "review": "评测观点",
}

# ── 18 个信息源 ──
SOURCES = [
    {"name": "GamesBeat", "url": "https://gamesbeat.com/", "rss": "https://venturebeat.com/category/games/feed/", "country": "US"},
    {"name": "Game Informer", "url": "https://gameinformer.com/", "rss": "https://www.gameinformer.com/rss.xml", "country": "US"},
    {"name": "Game Rant", "url": "https://gamerant.com/", "rss": "https://gamerant.com/feed/", "country": "US"},
    {"name": "Gameranx", "url": "https://gameranx.com/", "rss": None, "country": "US", "scrape": True, "scrape_url": "https://gameranx.com/"},
    {"name": "Giant Bomb", "url": "https://giantbomb.com/", "rss": "https://www.giantbomb.com/feeds/news/", "country": "US"},
    {"name": "IGN", "url": "https://www.ign.com/", "rss": "https://feeds.feedburner.com/ign/all", "country": "US"},
    {"name": "GameSpot", "url": "https://www.gamespot.com/", "rss": "https://www.gamespot.com/feeds/news/", "country": "US"},
    {"name": "Kotaku", "url": "https://kotaku.com/", "rss": "https://kotaku.com/rss", "country": "US"},
    {"name": "PC Gamer", "url": "https://www.pcgamer.com/", "rss": "https://www.pcgamer.com/rss/", "country": "US"},
    {"name": "Polygon", "url": "https://www.polygon.com/", "rss": "https://www.polygon.com/rss/index.xml", "country": "US"},
    {"name": "GamesIndustry", "url": "https://www.gamesindustry.biz/", "rss": "https://www.gamesindustry.biz/feed", "country": "US"},
    {"name": "Mobilegamer", "url": "https://mobilegamer.biz/", "rss": "https://mobilegamer.biz/feed/", "country": "US"},
    {"name": "PocketGamer.biz", "url": "https://www.pocketgamer.biz/", "rss": "https://www.pocketgamer.biz/rss.php", "country": "US"},
    {"name": "Dexerto", "url": "https://www.dexerto.com/", "rss": "https://www.dexerto.com/feed/", "country": "US"},
    {"name": "PocketGamer", "url": "https://www.pocketgamer.com/", "rss": "https://www.pocketgamer.com/feed/", "country": "US"},
    {"name": "游民星空", "url": "https://www.gamersky.com/", "rss": None, "country": "CN", "scrape": True, "scrape_url": "https://www.gamersky.com/news/"},
    {"name": "gamebiz", "url": "https://gamebiz.jp/", "rss": "https://gamebiz.jp/feed", "country": "JP"},
    {"name": "GameBusiness", "url": "https://www.gamebusiness.jp/", "rss": "https://www.gamebusiness.jp/rss20/index.rdf", "country": "JP"},
    {"name": "Edge", "url": "https://www.gamesradar.com/uk/edge/", "rss": "https://www.gamesradar.com/uk/edge/feed/", "country": "GB"},
    {"name": "Eurogamer", "url": "https://www.eurogamer.net/", "rss": "https://www.eurogamer.net/feed", "country": "GB"},
    {"name": "GamesRadar+", "url": "https://www.gamesradar.com/", "rss": "https://www.gamesradar.com/feed/", "country": "GB"},
    {"name": "GAMINGbible", "url": "https://www.gamingbible.com/", "rss": "https://www.gamingbible.com/feed", "country": "GB"},
    {"name": "PCGamesN", "url": "https://www.pcgamesn.com/", "rss": "https://www.pcgamesn.com/feed", "country": "GB"},
    {"name": "Pocket Tactics", "url": "https://www.pockettactics.com/", "rss": "https://www.pockettactics.com/feed", "country": "GB"},
    {"name": "Techradar Gaming", "url": "https://www.techradar.com/sg/gaming", "rss": "https://www.techradar.com/feeds/articletype/news/gaming", "country": "GB"},
    {"name": "VG247", "url": "https://www.vg247.com/", "rss": "https://www.vg247.com/feed", "country": "GB"},
    {"name": "VGC", "url": "https://www.videogameschronicle.com/", "rss": "https://www.videogameschronicle.com/feed/", "country": "GB"},
    {"name": "Infobae Gaming", "url": "https://www.infobae.com/malditos-nerds/", "rss": None, "country": "AR", "scrape": True, "scrape_url": "https://www.infobae.com/malditos-nerds/"},
    {"name": "Press Start", "url": "https://press-start.com.au/", "rss": "https://press-start.com.au/feed/", "country": "AU"},
    {"name": "Stevivor", "url": "https://stevivor.com/", "rss": "https://stevivor.com/feed/", "country": "AU"},
    {"name": "invader.be", "url": "https://invader.be/", "rss": None, "country": "BE", "scrape": True, "scrape_url": "https://invader.be/"},
    {"name": "Combo Infinito", "url": "https://www.comboinfinito.com.br/", "rss": None, "country": "BR", "scrape": True, "scrape_url": "https://www.comboinfinito.com.br/"},
    {"name": "Flow Games", "url": "https://flowgames.gg/", "rss": None, "country": "BR", "scrape": True, "scrape_url": "https://flowgames.gg/"},
    {"name": "A9VG", "url": "https://www.a9vg.com/", "rss": "https://www.a9vg.com/rss/data/sample", "country": "CN"},
    {"name": "Game Bonfire", "url": "https://gamebonfire.com/", "rss": None, "country": "CN", "scrape": True, "scrape_url": "https://gamebonfire.com/"},
    {"name": "GameCores", "url": "https://gcores.com/", "rss": "https://www.gcores.com/rss", "country": "CN"},
    {"name": "GamerFocus", "url": "https://www.gamerfocus.co/", "rss": "https://www.gamerfocus.co/feed/", "country": "CO"},
    {"name": "HTL", "url": "https://www.hcl.hr/", "rss": None, "country": "HR", "scrape": True, "scrape_url": "https://www.hcl.hr/"},
    {"name": "GAMES.CZ", "url": "https://games.tiscali.cz/", "rss": None, "country": "CZ", "scrape": True, "scrape_url": "https://games.tiscali.cz/"},
    {"name": "Gamereactor", "url": "https://www.gamereactor.dk/", "rss": "https://www.gamereactor.dk/rss/", "country": "DK"},
    {"name": "Pelit", "url": "https://www.pelit.fi/", "rss": None, "country": "FI", "scrape": True, "scrape_url": "https://www.pelit.fi/"},
    {"name": "ActuGaming", "url": "https://www.actugaming.net/", "rss": "https://www.actugaming.net/feed/", "country": "FR"},
    {"name": "GameBlog", "url": "https://www.gameblog.fr/", "rss": "https://www.gameblog.fr/rss.xml", "country": "FR"},
    {"name": "Gamekult", "url": "https://www.gamekult.com/", "rss": "https://www.gamekult.com/feed.xml", "country": "FR"},
    {"name": "Jeux Vidéo Magazine", "url": "https://www.jeuxvideomagazine.com/", "rss": None, "country": "FR", "scrape": True, "scrape_url": "https://www.jeuxvideomagazine.com/"},
    {"name": "JEUXACTU", "url": "https://www.jeuxactu.com/", "rss": "https://www.jeuxactu.com/rss/", "country": "FR"},
    {"name": "MGG", "url": "https://www.millenium.org/", "rss": None, "country": "FR", "scrape": True, "scrape_url": "https://www.millenium.org/"},
    {"name": "EarlyGame", "url": "https://earlygame.com/", "rss": "https://earlygame.com/feed", "country": "DE"},
    {"name": "GamePro", "url": "https://www.gamepro.de/", "rss": "https://www.gamepro.de/rss/news.rss", "country": "DE"},
    {"name": "GameStar", "url": "https://www.gamestar.de/", "rss": "https://www.gamestar.de/news/rss/news.rss", "country": "DE"},
    {"name": "Gameswelt", "url": "https://www.gameswelt.de/", "rss": "https://www.gameswelt.de/rss/news.xml", "country": "DE"},
    {"name": "M! Games", "url": "https://www.maniac.de/", "rss": None, "country": "DE", "scrape": True, "scrape_url": "https://www.maniac.de/"},
    {"name": "PC Games", "url": "https://www.pcgames.de/", "rss": "https://www.pcgames.de/rss/news.rss", "country": "DE"},
    {"name": "GSPlus", "url": "https://www.gsplus.hu/", "rss": None, "country": "HU", "scrape": True, "scrape_url": "https://www.gsplus.hu/"},
    {"name": "Gaming Bolt", "url": "https://gamingbolt.com/", "rss": "https://gamingbolt.com/feed", "country": "IN"},
    {"name": "Everyeye.it", "url": "https://www.everyeye.it/", "rss": "https://www.everyeye.it/feed/", "country": "IT"},
    {"name": "Multiplayer.it", "url": "https://multiplayer.it/", "rss": "https://multiplayer.it/feed/", "country": "IT"},
    {"name": "SpazioGames", "url": "https://www.spaziogames.it/", "rss": "https://www.spaziogames.it/feed/", "country": "IT"},
    {"name": "4Gamer", "url": "https://www.4gamer.net/", "rss": "https://www.4gamer.net/rss/index.xml", "country": "JP"},
    {"name": "Dengeki", "url": "https://hobby.dengeki.com/", "rss": None, "country": "JP", "scrape": True, "scrape_url": "https://hobby.dengeki.com/"},
    {"name": "Famitsu", "url": "https://www.famitsu.com/", "rss": "https://www.famitsu.com/feed/", "country": "JP"},
    {"name": "GAME Watch", "url": "https://game.watch.impress.co.jp/", "rss": None, "country": "JP", "scrape": True, "scrape_url": "https://game.watch.impress.co.jp/"},
    {"name": "Game*Spark", "url": "https://www.gamespark.jp/", "rss": "https://www.gamespark.jp/rss/index.rdf", "country": "JP"},
    {"name": "GamerBraves", "url": "https://www.gamerbraves.com/", "rss": "https://www.gamerbraves.com/feed/", "country": "MY"},
    {"name": "Kakuchopurei", "url": "https://www.kakuchopurei.com/", "rss": None, "country": "MY", "scrape": True, "scrape_url": "https://www.kakuchopurei.com/"},
    {"name": "Nmia Gaming", "url": "https://nmiagaming.com/", "rss": "https://nmiagaming.com/feed/", "country": "MY"},
    {"name": "3DJuegos LATAM", "url": "https://www.3djuegos.lat/", "rss": None, "country": "MX", "scrape": True, "scrape_url": "https://www.3djuegos.lat/"},
    {"name": "Atomix", "url": "https://atomix.vg/", "rss": "https://atomix.vg/feed/", "country": "MX"},
    {"name": "LevelUp", "url": "https://www.levelup.com/", "rss": "https://www.levelup.com/rss/noticias", "country": "MX"},
    {"name": "TierraGamer", "url": "https://tierragamer.com/", "rss": "https://tierragamer.com/feed/", "country": "MX"},
    {"name": "Saudi Gamer", "url": "https://www.saudigamer.com/", "rss": "https://www.saudigamer.com/feed/", "country": "SA"},
    {"name": "True Gaming", "url": "https://www.true-gaming.net/", "rss": "https://www.true-gaming.net/home/feed/", "country": "SA"},
    {"name": "Gamecored", "url": "https://gamecored.com/", "rss": None, "country": "PE", "scrape": True, "scrape_url": "https://gamecored.com/"},
    {"name": "One More Game", "url": "https://onemoregame.ph/", "rss": "https://onemoregame.ph/feed/", "country": "PH"},
    {"name": "Sirus Gaming", "url": "https://sirusgaming.com/", "rss": "https://sirusgaming.com/feed/", "country": "PH"},
    {"name": "UnGEEK", "url": "https://www.ungeek.ph/", "rss": "https://www.ungeek.ph/feed/", "country": "PH"},
    {"name": "CD-Action", "url": "https://cdaction.pl/", "rss": "https://cdaction.pl/rss/news.xml", "country": "PL"},
    {"name": "GRYOnline", "url": "https://www.gry-online.pl/", "rss": "https://www.gry-online.pl/rss/news.xml", "country": "PL"},
    {"name": "Geek Culture", "url": "https://geekculture.co/", "rss": "https://geekculture.co/feed/", "country": "SG"},
    {"name": "GLITCHED Africa", "url": "https://www.glitched.online/", "rss": "https://www.glitched.online/feed/", "country": "ZA"},
    {"name": "RULIWEB", "url": "https://m.ruliweb.com/", "rss": None, "country": "KR", "scrape": True, "scrape_url": "https://m.ruliweb.com/"},
    {"name": "ThisisGame", "url": "https://www.thisisgame.com/", "rss": None, "country": "KR", "scrape": True, "scrape_url": "https://www.thisisgame.com/"},
    {"name": "3DJuegos", "url": "https://www.3djuegos.com/", "rss": "https://www.3djuegos.com/rss.xml", "country": "ES"},
    {"name": "Alfa Beta Juega", "url": "https://alfabetajuega.com/", "rss": None, "country": "ES", "scrape": True, "scrape_url": "https://alfabetajuega.com/"},
    {"name": "Hobby Consolas", "url": "https://www.hobbyconsolas.com/", "rss": "https://www.hobbyconsolas.com/rss.xml", "country": "ES"},
    {"name": "MeriStation", "url": "https://as.com/meristation/", "rss": "https://as.com/meristation/rss.xml", "country": "ES"},
    {"name": "Vandal", "url": "https://vandal.elespanol.com/", "rss": "https://vandal.elespanol.com/rss.xml", "country": "ES"},
    {"name": "FZ", "url": "https://www.fz.se/", "rss": "https://www.fz.se/feed", "country": "SE"},
    {"name": "Games.ch", "url": "https://www.games.ch/", "rss": None, "country": "CH", "scrape": True, "scrape_url": "https://www.games.ch/"},
    {"name": "Bahamut", "url": "https://www.gamer.com.tw/", "rss": "https://www.gamer.com.tw/rss.xml", "country": "TW"},
    {"name": "udngame", "url": "https://game.udn.com/game/index", "rss": None, "country": "TW", "scrape": True, "scrape_url": "https://game.udn.com/game/index"},
    {"name": "GamingDose", "url": "https://www.gamingdose.com/", "rss": None, "country": "TH", "scrape": True, "scrape_url": "https://www.gamingdose.com/"},
    {"name": "Oyungezer", "url": "https://oyungezer.com.tr/", "rss": None, "country": "TR", "scrape": True, "scrape_url": "https://oyungezer.com.tr/"},
    {"name": "Kokang Gaming", "url": "https://kokanggaming.com/", "rss": None, "country": "ID", "scrape": True, "scrape_url": "https://kokanggaming.com/"},
    {"name": "Kotak Game", "url": "http://www.kotakgame.com/", "rss": None, "country": "ID", "scrape": True, "scrape_url": "http://www.kotakgame.com/"},
    {"name": "Arkaden", "url": "https://arkaden.dk/", "rss": None, "country": "DK", "scrape": True, "scrape_url": "https://arkaden.dk/"},
    {"name": "91 Mobiles", "url": "https://www.91mobiles.com/game-zone", "rss": None, "country": "IN", "scrape": True, "scrape_url": "https://www.91mobiles.com/game-zone"},
    {"name": "Power Unlimited", "url": "https://pu.nl/", "rss": None, "country": "NL", "scrape": True, "scrape_url": "https://pu.nl/"},
    {"name": "Volk", "url": "https://www.noticiascaracol.com/videojuegos", "rss": None, "country": "CO", "scrape": True, "scrape_url": "https://www.noticiascaracol.com/videojuegos"},
    {"name": "Reporte Indigo", "url": "https://geek.reporteindigo.com/", "rss": None, "country": "MX", "scrape": True, "scrape_url": "https://geek.reporteindigo.com/"},
    {"name": "VGA4A", "url": "https://www.vga4a.com/", "rss": None, "country": "SA", "scrape": True, "scrape_url": "https://www.vga4a.com/"},
    {"name": "Nos Dicen Gamers", "url": "https://nosdicengamers.com/", "rss": None, "country": "PE", "scrape": True, "scrape_url": "https://nosdicengamers.com/"},
    {"name": "Online Station", "url": "https://www.online-station.net/", "rss": None, "country": "TH", "scrape": True, "scrape_url": "https://www.online-station.net/"},
    {"name": "This is Game Thailand", "url": "https://thisisgamethailand.com/", "rss": None, "country": "TH", "scrape": True, "scrape_url": "https://thisisgamethailand.com/"},
    {"name": "Atarita", "url": "https://www.atarita.com/", "rss": None, "country": "TR", "scrape": True, "scrape_url": "https://www.atarita.com/"},
]


def _parse_rss(root, source, since_hours=24):
    """从已解析的 XML 根节点提取 RSS 文章"""
    articles = []
    cutoff = NOW - timedelta(hours=since_hours)

    for item in root.iter("item"):
        try:
            title = item.find("title").text or ""
            link = item.find("link").text or ""
            pub_str = (item.find("pubDate") or item.find("dc:date"))
            pub_str = pub_str.text if pub_str is not None and pub_str.text else None
            desc = item.find("description")
            desc = desc.text if desc is not None else ""

            # 时间解析
            pub_dt = None
            if pub_str:
                for fmt in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%d %H:%M:%S",
                ]:
                    try:
                        pub_dt = datetime.strptime(pub_str.strip(), fmt)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            if pub_dt and pub_dt < cutoff:
                continue

            # 去 HTML 标签
            title = re.sub(r"<[^>]+>", "", title).strip()
            desc = re.sub(r"<[^>]+>", "", desc).strip()[:200]

            if title and link:
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source["name"],
                    "country": source["country"],
                    "published_at": pub_dt.isoformat() if pub_dt else None,
                    "summary": desc,
                    "category": guess_category(title, desc),
                })
        except Exception:
            continue

    return articles


def _parse_atom(root, source, since_hours=24):
    """从已解析的 XML 根节点提取 Atom 文章"""
    articles = []
    cutoff = NOW - timedelta(hours=since_hours)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        try:
            title = entry.find("atom:title", ns)
            title = title.text if title is not None else ""
            title = re.sub(r"<[^>]+>", "", title).strip()

            link_el = entry.find("atom:link[@rel='alternate']") or entry.find("atom:link")
            if link_el is None:
                link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""

            pub_el = entry.find("atom:published", ns) or entry.find("atom:updated", ns)
            pub_str = pub_el.text if pub_el is not None else None

            summary_el = entry.find("atom:summary", ns)
            summary = summary_el.text if summary_el is not None else ""
            summary = re.sub(r"<[^>]+>", "", summary).strip()[:200]

            pub_dt = None
            if pub_str:
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%SZ",
                ]:
                    try:
                        pub_dt = datetime.strptime(pub_str.strip(), fmt)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            if pub_dt and pub_dt < cutoff:
                continue

            if title and link:
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source["name"],
                    "country": source["country"],
                    "published_at": pub_dt.isoformat() if pub_dt else None,
                    "summary": summary,
                    "category": guess_category(title, summary),
                })
        except Exception:
            continue

    return articles


def fetch_feed(source, since_hours=24):
    """单次请求拉取 RSS/Atom 并解析"""
    try:
        resp = get_session().get(source["rss"], timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"  ⚠ {source['name']} Feed 失败: {e}", file=sys.stderr)
        return []

    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag == "feed":
        return _parse_atom(root, source, since_hours)
    return _parse_rss(root, source, since_hours)


def fetch_gamersky(since_hours=24):
    """抓取游民星空新闻列表页"""
    articles = []
    try:
        resp = get_session().get(
            "https://www.gamersky.com/news/",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        # 游民星空使用 GBK 编码
        resp.encoding = "gbk"
        html = resp.text
    except Exception as e:
        print(f"  ⚠ 游民星空 抓取失败: {e}", file=sys.stderr)
        return articles

    # 提取标题、URL、时间
    pattern = r'<div class="tit"><a[^>]*href="([^"]*)"[^>]*>(?:<font[^>]*>)?([^<]+)(?:</font>)?</a></div>.*?<div class="time">(\d{4}-\d{2}-\d{2} \d{2}:\d{2})</div>'
    matches = re.findall(pattern, html, re.DOTALL)
    seen_urls = set()

    for url, title, ts in matches:
        url = url.strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 相对 URL 补全
        if url.startswith("/"):
            url = f"https://www.gamersky.com{url}"

        title = title.strip()

        # 时间过滤
        try:
            pub_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M")
            pub_dt = pub_dt.replace(tzinfo=BEIJING)
            cutoff = NOW - timedelta(hours=since_hours)
            if pub_dt < cutoff:
                continue
        except ValueError:
            continue

        # 过滤非游戏内容
        if _is_non_gaming(title):
            continue

        articles.append({
            "title": title,
            "url": url,
            "source": "游民星空",
            "country": "CN",
            "published_at": pub_dt.isoformat(),
            "summary": "",
            "category": guess_category(title, ""),
        })

    return articles


def fetch_gameranx(since_hours=24):
    """抓取 Gameranx 首页"""
    articles = []
    try:
        resp = get_session().get(
            "https://gameranx.com/",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  ⚠ Gameranx 抓取失败: {e}", file=sys.stderr)
        return articles

    # Extract article titles and links from the homepage
    pattern = r'<h\d[^>]*class="[^"]*entry-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.DOTALL)
    seen_urls = set()

    for url, title in matches:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = title.strip()
        if title:
            articles.append({
                "title": title,
                "url": url,
                "source": "Gameranx",
                "country": "US",
                "published_at": None,
                "summary": "",
                "category": guess_category(title, ""),
            })

    return articles[:20]


def _is_non_gaming(title):
    """过滤非游戏内容"""
    non_gaming = [
        "乃木坂", "朱自清", "碳水", "燃油", "房价", "股票",
        "裴斗娜", "穿搭", "美妆", "减肥", "养生",
    ]
    return any(kw in title for kw in non_gaming)


def guess_category(title, summary):
    """基于关键词猜测文章分类"""
    text = (title + " " + summary).lower()
    if any(kw in text for kw in ["发布", "上线", "推出", "发售", "release", "launch", "announce", "公布", "定档"]):
        return "new-game"
    if any(kw in text for kw in ["显卡", "cpu", "gpu", "硬件", "hardware", "芯片", "ssd", "内存", "显示器"]):
        return "hardware"
    if any(kw in text for kw in ["电竞", "比赛", "战队", "冠军", "esports", "联赛", "锦标赛", "tournament"]):
        return "esports"
    if any(kw in text for kw in ["评测", "测评", "review", "上手", "试玩", "体验", "评分", "打分"]):
        return "review"
    return "industry"


def fetch_source(source, since_hours=24):
    """抓取单个信息源"""
    if source.get("scrape"):
        if "gamersky" in source.get("scrape_url", ""):
            articles = fetch_gamersky(since_hours)
        elif "gameranx" in source.get("scrape_url", ""):
            articles = fetch_gameranx(since_hours)
        else:
            articles = []
    elif source.get("rss"):
        articles = fetch_feed(source, since_hours)
    else:
        articles = []

    with _print_lock:
        print(f"  📡 {source['name']}... {len(articles)} 条", flush=True)
    return articles


def deduplicate(articles):
    """URL 去重，保留最早的"""
    seen = {}
    for a in articles:
        url = a["url"]
        if url not in seen or (a.get("published_at") and (
            not seen[url].get("published_at") or a["published_at"] < seen[url]["published_at"]
        )):
            seen[url] = a
    return sorted(seen.values(), key=lambda x: x.get("published_at") or "", reverse=True)


def _is_chinese(text):
    """检测文本是否包含中文"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def translate_articles(articles):
    """将非中文标题翻译为中文（DeepSeek API）"""
    import os
    from urllib.request import Request, urlopen

    # 过滤需要翻译的文章
    need_trans = [a for a in articles if not _is_chinese(a["title"])]
    if not need_trans:
        return articles

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        # Fallback: try hermes config
        try:
            import yaml
            localappdata = os.environ.get("LOCALAPPDATA", "")
            cfg_path = os.path.join(localappdata, "hermes", "config.yaml")
            cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
            api_key = cfg.get("model", {}).get("api_key", "")
            base_url = cfg.get("model", {}).get("base_url", "https://api.deepseek.com/v1")
        except Exception as e:
            print(f"  ⚠ 读取配置失败: {e}，跳过翻译", file=sys.stderr)
            return articles
    else:
        base_url = "https://api.deepseek.com/v1"

    if not api_key:
        print("  ⚠ 无 API Key，跳过翻译", file=sys.stderr)
        return articles

    print(f"  🌐 DeepSeek 翻译 {len(need_trans)} 条标题 ...", flush=True)

    # Batch translate: 50 titles per API call
    batch_size = 50
    for batch_start in range(0, len(need_trans), batch_size):
        batch = need_trans[batch_start:batch_start + batch_size]
        titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(batch)])

        try:
            payload = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是游戏新闻翻译。把以下英文标题翻译成简洁中文。只返回翻译结果，每行一个，不要序号，不要解释。"},
                    {"role": "user", "content": titles}
                ],
                "temperature": 0.1,
                "max_tokens": len(batch) * 60
            }).encode("utf-8")

            req = Request(f"{base_url}/chat/completions", data=payload, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
            resp = urlopen(req, timeout=30)
            result = json.loads(resp.read().decode("utf-8"))
            translated = result["choices"][0]["message"]["content"].strip().split("\n")

            for i, a in enumerate(batch):
                if i < len(translated):
                    t = re.sub(r'^\d+[\.\、\s]+', '', translated[i]).strip()
                    a["title_cn"] = t if t else a["title"]
                else:
                    a["title_cn"] = a["title"]
        except Exception as e:
            for a in batch:
                a["title_cn"] = a["title"]

        done = min(batch_start + batch_size, len(need_trans))
        print(f"    翻译进度: {done}/{len(need_trans)}", flush=True)

    print(f"  ✅ 翻译完成", flush=True)
    return articles


def time_to_human(pub_str):
    """ISO 时间 → 人话"""
    if not pub_str:
        return ""
    try:
        dt = datetime.fromisoformat(pub_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_bj = dt.astimezone(BEIJING)
        diff = NOW - dt_bj
        if diff < timedelta(minutes=1):
            return "刚刚"
        if diff < timedelta(hours=1):
            return f"{int(diff.total_seconds()//60)}分钟前"
        if diff < timedelta(hours=24):
            return f"{int(diff.total_seconds()//3600)}小时前"
        return dt_bj.strftime("%m/%d %H:%M")
    except Exception:
        return ""


def generate_html(articles, since_hours=24):
    """生成日报 HTML，参照 AI HOT 格式 + 游戏杂志风格"""
    # 按分类分组
    grouped = {}
    for a in articles:
        cat = a.get("category", "industry")
        grouped.setdefault(cat, []).append(a)

    # 生成各分类 HTML
    sections = []
    total = 0
    cat_order = ["new-game", "industry", "hardware", "esports", "review"]
    n = 1

    for cat_key in cat_order:
        cat_items = grouped.pop(cat_key, [])
        if not cat_items:
            continue

        items_html = ""
        for a in cat_items:
            time_str = time_to_human(a.get("published_at"))
            summary = a.get("summary", "")[:120]
            subtitle = f'<p class="subtitle">{a["title"]}</p>' if a.get('title_cn') and a.get('title_cn') != a['title'] else ''
            items_html += f"""<div class="item">
  <span class="num">#{n}</span>
  <div class="item-body">
    <a href="{a['url']}" class="title" target="_blank">{a.get('title_cn', a['title'])}</a>
    {subtitle}
    <span class="source">{a['source']}</span>
    <span class="time">{time_str}</span>
    {f'<p class="summary">{summary}</p>' if summary else ''}
  </div>
</div>
"""
            n += 1
            total += 1

        sections.append(f"""<div class="section">
<h2>{CATS[cat_key]}</h2>
{items_html}
</div>""")

    # 剩余分类
    for cat_key, cat_items in grouped.items():
        if not cat_items:
            continue
        items_html = ""
        for a in cat_items:
            time_str = time_to_human(a.get("published_at"))
            subtitle = f'<p class="subtitle">{a["title"]}</p>' if a.get('title_cn') and a.get('title_cn') != a['title'] else ''
            items_html += f"""<div class="item">
  <span class="num">#{n}</span>
  <div class="item-body">
    <a href="{a['url']}" class="title" target="_blank">{a.get('title_cn', a['title'])}</a>
    {subtitle}
    <span class="source">{a['source']}</span>
    <span class="time">{time_str}</span>
  </div>
</div>
"""
            n += 1
            total += 1
        sections.append(f'<div class="section"><h2>{CATS.get(cat_key, "其他")}</h2>{items_html}</div>')

    body = "\n".join(sections)

    window_text = f"过去{since_hours}小时" if since_hours < 24 else f"过去{since_hours//24}天"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>狼叔的游戏雷达 · {TODAY}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0d0d0f;
    color: #d0d0d0;
    font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 32px 24px 60px;
    line-height: 1.7;
  }}
  header {{
    text-align: center;
    padding: 24px 0 36px;
    border-bottom: 3px solid #c0392b;
    margin-bottom: 36px;
  }}
  header .label {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.78em;
    color: #c0392b;
    letter-spacing: 4px;
    margin-bottom: 8px;
  }}
  h1 {{
    font-family: 'Oswald', 'Noto Sans SC', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 2px;
    margin-bottom: 8px;
  }}
  h1 span {{ font-weight: 300; color: #888; }}
  .sub {{ font-size: 13px; color: #666; }}
  .section {{ margin-bottom: 36px; }}
  h2 {{
    font-family: 'Oswald', sans-serif;
    font-size: 16px;
    color: #c0392b;
    letter-spacing: 2px;
    border-left: 3px solid #c0392b;
    padding-left: 12px;
    margin-bottom: 16px;
  }}
  .item {{
    background: #141418;
    border: 1px solid #1f1f24;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
    display: flex;
    gap: 12px;
    align-items: flex-start;
    transition: border-color .15s;
  }}
  .item:hover {{ border-color: #c0392b55; }}
  .num {{
    color: #c0392b;
    font-family: 'Oswald', sans-serif;
    font-size: 14px;
    min-width: 28px;
    padding-top: 2px;
  }}
  .item-body {{ flex: 1; min-width: 0; }}
  .title {{
    color: #e8e8ec;
    font-weight: 600;
    font-size: 15px;
    text-decoration: none;
  }}
  .title:hover {{ color: #c0392b; }}
  .source {{
    color: #555;
    font-size: 12px;
    margin-left: 8px;
  }}
  .time {{
    color: #555;
    font-size: 11px;
    margin-left: 8px;
  }}
  .summary {{
    color: #888;
    font-size: 13px;
    margin-top: 4px;
    line-height: 1.6;
  }}
  .subtitle {{
    color: #555;
    font-size: 12px;
    margin-top: 1px;
    font-style: italic;
  }}
  footer {{
    text-align: center;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #1f1f24;
    font-size: 12px;
    color: #555;
    font-family: 'Oswald', sans-serif;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
<header>
  <div class="label">FIREWOLF'S GAME RADAR</div>
  <h1>狼叔的<span>游戏雷达</span></h1>
  <div class="sub">{TODAY} · {window_text} · 共 {total} 条</div>
</header>
{body}
<footer>狼叔的游戏雷达 · 数据来自 全球游戏媒体信源</footer>
</body>
</html>"""

    return html


def _format_duration(seconds):
    """秒数 → 可读耗时"""
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes} 分 {secs:.1f} 秒"


def main():
    since_hours = 24
    if len(sys.argv) > 1:
        try:
            since_hours = int(sys.argv[1])
        except ValueError:
            pass

    scrape_start = time.perf_counter()

    print(f"🎮 狼叔的游戏雷达 · 抓取中（过去 {since_hours} 小时）")
    print(f"   时间: {NOW.strftime('%Y-%m-%d %H:%M')} 北京时间\n")

    all_articles = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_source, src, since_hours): src for src in SOURCES}
        for future in as_completed(futures):
            try:
                all_articles.extend(future.result())
            except Exception as e:
                src = futures[future]
                print(f"  ⚠ {src['name']} 异常: {e}", file=sys.stderr)

    scrape_elapsed = time.perf_counter() - scrape_start

    # 去重
    unique = deduplicate(all_articles)
    print(f"\n✅ 共抓取 {len(all_articles)} 条 → 去重后 {len(unique)} 条")

    # 翻译（国内被墙，默认关闭。GitHub Actions 上自动启用）
    if '--translate' in sys.argv:
        unique = translate_articles(unique)

    if not unique:
        print("⚠ 没有抓取到任何新闻！")
        # Generate empty report
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>狼叔的游戏雷达 · {TODAY}</title></head>
<body style="background:#0d0d0f;color:#d0d0d0;font-family:sans-serif;text-align:center;padding:100px 20px;">
<h1 style="color:#c0392b;">狼叔的游戏雷达 · {TODAY}</h1>
<p>暂无新闻数据，请稍后再试。</p>
<p style="color:#666;font-size:13px;">数据来自 全球游戏媒体信源</p>
</body></html>"""

    else:
        # 生成 HTML
        html = generate_html(unique, since_hours)

    # 保存
    out_path = OUTPUT_DIR / f"index.html"
    out_path.write_text(html, encoding="utf-8")

    # 同时保存日期版本
    date_path = OUTPUT_DIR / f"archive" / f"{TODAY}.html"
    date_path.parent.mkdir(exist_ok=True)
    date_path.write_text(html, encoding="utf-8")

    # 保存 JSON 数据
    json_path = OUTPUT_DIR / "latest.json"
    json_path.write_text(json.dumps({
        "date": TODAY,
        "generated_at": NOW.isoformat(),
        "since_hours": since_hours,
        "total": len(unique),
        "articles": unique,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"📄 HTML 已保存: {out_path}")
    print(f"📁 归档: {date_path}")
    print(f"📊 JSON: {json_path}")
    print(f"⏱️  爬取耗时: {_format_duration(scrape_elapsed)}")
    print(f"\n🎉 完成！")


if __name__ == "__main__":
    main()
