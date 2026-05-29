"""
狼叔的游戏雷达 - RSS/网页抓取脚本
抓取 18 个游戏媒体源，生成日报 HTML
参照 AI HOT 输出规范
"""
import json
import re
import sys
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Installing requests...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# ── Config ──
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TIMEOUT = 20
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
    # ===== 美国 =====
    {"name": "GamesBeat", "url": "https://gamesbeat.com/", "rss": "https://venturebeat.com/category/games/feed/", "country": "US", "scrape": False},
    {"name": "Game Informer", "url": "https://gameinformer.com/", "rss": "https://www.gameinformer.com/rss.xml", "country": "US", "scrape": False},
    {"name": "Game Rant", "url": "https://gamerant.com/", "rss": "https://gamerant.com/feed/", "country": "US", "scrape": False},
    {"name": "Gameranx", "url": "https://gameranx.com/", "rss": None, "country": "US", "scrape": True, "scrape_url": "https://gameranx.com/"},
    {"name": "Giant Bomb", "url": "https://giantbomb.com/", "rss": "https://www.giantbomb.com/feeds/news/", "country": "US", "scrape": False},
    {"name": "IGN", "url": "https://www.ign.com/", "rss": "https://feeds.feedburner.com/ign/all", "country": "US", "scrape": False},
    {"name": "GameSpot", "url": "https://www.gamespot.com/", "rss": "https://www.gamespot.com/feeds/news/", "country": "US", "scrape": False},
    {"name": "Kotaku", "url": "https://kotaku.com/", "rss": "https://kotaku.com/rss", "country": "US", "scrape": False},
    {"name": "PC Gamer", "url": "https://www.pcgamer.com/", "rss": "https://www.pcgamer.com/rss/", "country": "US", "scrape": False},
    {"name": "Polygon", "url": "https://www.polygon.com/", "rss": "https://www.polygon.com/rss/index.xml", "country": "US", "scrape": False},
    {"name": "GamesIndustry", "url": "https://www.gamesindustry.biz/", "rss": "https://www.gamesindustry.biz/feed", "country": "US", "scrape": False},
    {"name": "Mobilegamer", "url": "https://mobilegamer.biz/", "rss": "https://mobilegamer.biz/feed/", "country": "US", "scrape": False},
    {"name": "PocketGamer.biz", "url": "https://www.pocketgamer.biz/", "rss": "https://www.pocketgamer.biz/rss.php", "country": "US", "scrape": False},
    {"name": "Dexerto", "url": "https://www.dexerto.com/", "rss": "https://www.dexerto.com/feed/", "country": "US", "scrape": False},
    {"name": "PocketGamer", "url": "https://www.pocketgamer.com/", "rss": "https://www.pocketgamer.com/feed/", "country": "US", "scrape": False},
    # ===== 中国 =====
    {"name": "游民星空", "url": "https://www.gamersky.com/", "rss": None, "country": "CN", "scrape": True, "scrape_url": "https://www.gamersky.com/news/"},
    # ===== 日本 =====
    {"name": "gamebiz", "url": "https://gamebiz.jp/", "rss": "https://gamebiz.jp/feed", "country": "JP", "scrape": False},
    {"name": "GameBusiness", "url": "https://www.gamebusiness.jp/", "rss": "https://www.gamebusiness.jp/rss20/index.rdf", "country": "JP", "scrape": False},
]


def fetch_rss(source, since_hours=24):
    """拉 RSS 并解析，返回文章列表"""
    articles = []
    try:
        resp = requests.get(source["rss"], headers={"User-Agent": UA}, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"  ⚠ {source['name']} RSS 失败: {e}", file=sys.stderr)
        return articles

    # RSS 2.0
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

            if pub_dt:
                cutoff = NOW - timedelta(hours=since_hours)
                if pub_dt < cutoff:
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
        except Exception as e:
            continue

    return articles


def fetch_atom(source, since_hours=24):
    """拉 Atom feed"""
    articles = []
    try:
        resp = requests.get(source["rss"], headers={"User-Agent": UA}, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"  ⚠ {source['name']} Atom 失败: {e}", file=sys.stderr)
        return articles

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

            if pub_dt:
                cutoff = NOW - timedelta(hours=since_hours)
                if pub_dt < cutoff:
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


def fetch_gamersky(since_hours=24):
    """抓取游民星空新闻列表页"""
    articles = []
    try:
        resp = requests.get(
            "https://www.gamersky.com/news/",
            headers={"User-Agent": UA},
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
        resp = requests.get(
            "https://gameranx.com/",
            headers={"User-Agent": UA},
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
    print(f"  📡 {source['name']}...", end=" ", flush=True)
    articles = []

    if source.get("scrape"):
        if "gamersky" in source.get("scrape_url", ""):
            articles = fetch_gamersky(since_hours)
        elif "gameranx" in source.get("scrape_url", ""):
            articles = fetch_gameranx(since_hours)
    elif source.get("rss"):
        articles = fetch_rss(source, since_hours)
        if not articles:
            articles = fetch_atom(source, since_hours)

    print(f"{len(articles)} 条", flush=True)
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
            items_html += f"""<div class="item">
  <span class="num">#{n}</span>
  <div class="item-body">
    <a href="{a['url']}" class="title" target="_blank">{a['title']}</a>
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
            items_html += f"""<div class="item">
  <span class="num">#{n}</span>
  <div class="item-body">
    <a href="{a['url']}" class="title" target="_blank">{a['title']}</a>
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
<title>游戏雷达 · {TODAY}</title>
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
  <h1>游戏<span>雷达</span></h1>
  <div class="sub">{TODAY} · {window_text} · 共 {total} 条</div>
</header>
{body}
<footer>狼叔的游戏雷达 · 数据来自 18 个全球游戏媒体信源</footer>
</body>
</html>"""

    return html


def main():
    since_hours = 24
    if len(sys.argv) > 1:
        try:
            since_hours = int(sys.argv[1])
        except ValueError:
            pass

    print(f"🎮 狼叔的游戏雷达 · 抓取中（过去 {since_hours} 小时）")
    print(f"   时间: {NOW.strftime('%Y-%m-%d %H:%M')} 北京时间\n")

    all_articles = []
    for src in SOURCES:
        articles = fetch_source(src, since_hours)
        all_articles.extend(articles)
        time.sleep(1)  # 礼貌间隔

    # 去重
    unique = deduplicate(all_articles)
    print(f"\n✅ 共抓取 {len(all_articles)} 条 → 去重后 {len(unique)} 条")

    if not unique:
        print("⚠ 没有抓取到任何新闻！")
        # Generate empty report
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>游戏雷达 · {TODAY}</title></head>
<body style="background:#0d0d0f;color:#d0d0d0;font-family:sans-serif;text-align:center;padding:100px 20px;">
<h1 style="color:#c0392b;">游戏雷达 · {TODAY}</h1>
<p>暂无新闻数据，请稍后再试。</p>
<p style="color:#666;font-size:13px;">数据来自 18 个全球游戏媒体信源</p>
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
    print(f"\n🎉 完成！")


if __name__ == "__main__":
    main()
