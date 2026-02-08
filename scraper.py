"""
Naver Blog Scraper
- Search API (requests): 검색 결과 목록 + 총 게시물 수
- Playwright: 개별 게시물 상세 (본문 전체, 좋아요, 댓글)
"""

import json
import math
import re
import time
import random
import threading
import requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


SEARCH_API = "https://section.blog.naver.com/ajax/SearchList.naver"
ITEMS_PER_PAGE = 7
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://section.blog.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def count_posts(keyword: str, start_date: str, end_date: str) -> int:
    """키워드와 날짜 범위로 총 게시물 수를 조회합니다."""
    params = {
        "countPerPage": ITEMS_PER_PAGE,
        "currentPage": 1,
        "endDate": end_date,
        "keyword": keyword,
        "orderBy": "recentdate",
        "startDate": start_date,
        "type": "post",
    }
    resp = requests.get(SEARCH_API, params=params, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    data = _parse_naver_json(resp.text)
    return data["result"]["totalCount"]


def fetch_search_list(keyword: str, start_date: str, end_date: str) -> list[dict]:
    """검색 API를 페이지별로 호출하여 전체 게시물 메타데이터 리스트를 반환합니다."""
    total = count_posts(keyword, start_date, end_date)
    total_pages = math.ceil(total / ITEMS_PER_PAGE)
    all_posts = []

    for page in range(1, total_pages + 1):
        params = {
            "countPerPage": ITEMS_PER_PAGE,
            "currentPage": page,
            "endDate": end_date,
            "keyword": keyword,
            "orderBy": "recentdate",
            "startDate": start_date,
            "type": "post",
        }
        resp = requests.get(
            SEARCH_API, params=params, headers=REQUEST_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = _parse_naver_json(resp.text)

        for item in data["result"]["searchList"]:
            all_posts.append(
                {
                    "url": item["postUrl"],
                    "title": _strip_html(item.get("title", "")),
                    "author": item.get("nickName", ""),
                    "blog_name": item.get("blogName", ""),
                    "date": _format_timestamp(item.get("addDate", 0)),
                    "blog_id": item.get("domainIdOrBlogId", ""),
                    "log_no": item.get("logNo", 0),
                    "snippet": _strip_html(item.get("contents", "")),
                }
            )

        # 요청 간 딜레이
        if page < total_pages:
            time.sleep(random.uniform(0.3, 0.8))

    return all_posts


def scrape_post_detail(
    page, post_meta: dict, fields: list[str] | None = None, content_mode: str = "full"
) -> dict:
    """Playwright page를 사용하여 개별 게시물의 상세 정보를 스크래핑합니다."""
    url = post_meta["url"]
    result = {
        **post_meta,
        "content": post_meta.get("snippet", "") if content_mode == "preview" else "",
        "likes": 0,
        "comments": 0,
    }

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        # iframe 로드 대기
        page.wait_for_timeout(2000)

        # 네이버 블로그는 전체가 iframe 안에 있음
        frames = page.frames
        content_frame = None
        for f in frames:
            if f.url and "PostView" in f.url:
                content_frame = f
                break

        if content_frame is None and len(frames) > 1:
            content_frame = frames[1]

        if content_frame is None:
            content_frame = page

        # 본문 텍스트 추출 (전체 내용 모드일 때만)
        if content_mode == "full":
            content = _extract_content(content_frame)
            result["content"] = content

        # 좋아요/댓글 영역은 비동기 로드됨 — 렌더링 대기
        if fields is None or "likes" in fields or "comments" in fields:
            try:
                content_frame.wait_for_selector(
                    "span.u_likeit_list_count._count, #floating_bottom_commentCount",
                    timeout=5000,
                )
            except Exception:
                pass  # 타임아웃 시에도 추출 시도

        # 좋아요 수 추출 (필드 선택에 포함된 경우에만)
        if fields is None or "likes" in fields:
            likes = _extract_likes(content_frame)
            result["likes"] = likes

        # 댓글 수 추출 (필드 선택에 포함된 경우에만)
        if fields is None or "comments" in fields:
            comments = _extract_comments(content_frame)
            result["comments"] = comments

    except PlaywrightTimeoutError:
        if content_mode == "full":
            result["content"] = "[타임아웃: 페이지 로드 실패]"
    except Exception as e:
        if content_mode == "full":
            result["content"] = f"[오류: {str(e)[:200]}]"

    return result


def _check_controls(
    pause_event: threading.Event | None,
    stop_event: threading.Event | None,
    sleep_duration: float,
) -> bool:
    """일시정지/정지 이벤트를 확인하고 딜레이를 적용합니다.

    Returns:
        True면 정지해야 함, False면 계속 진행.
    """
    # 정지 확인
    if stop_event is not None and stop_event.is_set():
        return True

    # 딜레이 적용 (rate limiting)
    time.sleep(sleep_duration)

    # 딜레이 후 정지 재확인
    if stop_event is not None and stop_event.is_set():
        return True

    # 일시정지 대기 (pause_event가 clear 상태면 set될 때까지 무한 대기,
    # set 상태면 즉시 반환)
    if pause_event is not None:
        pause_event.wait()

    # 일시정지에서 풀린 후 정지 재확인 (일시정지 중 정지가 요청되었을 수 있음)
    if stop_event is not None and stop_event.is_set():
        return True

    return False


def scrape_all_posts(
    keyword: str,
    start_date: str,
    end_date: str,
    progress_callback=None,
    fields: list[str] | None = None,
    content_mode: str = "preview",
    pause_event: threading.Event | None = None,
    stop_event: threading.Event | None = None,
):
    """전체 스크래핑 프로세스: 검색 → 상세 스크래핑 (generator)

    Args:
        fields: 수집할 필드 목록. None이면 전체 필드 (하위 호환).
        content_mode: "preview" (검색 API 스니펫), "full" (Playwright 전체 내용), "none" (내용 없음)
        pause_event: threading.Event — set=실행중, clear=일시정지. None이면 무시.
        stop_event: threading.Event — set=정지요청. None이면 무시.
    """
    posts = fetch_search_list(keyword, start_date, end_date)
    total = len(posts)

    # Playwright가 필요한지 판단
    need_playwright = (
        content_mode == "full"
        or (fields is not None and ("likes" in fields or "comments" in fields))
        or fields is None  # 하위 호환: 전체 필드 = Playwright 필요
    )

    if need_playwright:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    locale="ko-KR",
                )
                page = context.new_page()

                for i, post_meta in enumerate(posts):
                    # 스크래핑 전 정지 확인
                    if stop_event is not None and stop_event.is_set():
                        break

                    detail = scrape_post_detail(
                        page, post_meta, fields=fields, content_mode=content_mode
                    )
                    if progress_callback:
                        progress_callback(i + 1, total, detail)
                    yield detail

                    # 요청 간 딜레이 + 일시정지/정지 확인
                    if i < total - 1:
                        should_stop = _check_controls(
                            pause_event, stop_event, random.uniform(0.8, 1.5)
                        )
                        if should_stop:
                            break
            finally:
                browser.close()
    else:
        # API 전용 모드: Playwright 없이 검색 API 데이터만 반환
        for i, post_meta in enumerate(posts):
            # 정지 확인
            if stop_event is not None and stop_event.is_set():
                break

            result = {**post_meta}
            if content_mode == "preview":
                result["content"] = post_meta.get("snippet", "")
            elif content_mode == "none":
                result["content"] = ""
            result["likes"] = 0
            result["comments"] = 0

            if progress_callback:
                progress_callback(i + 1, total, result)
            yield result

            # SSE 스트리밍 일관성을 위한 짧은 딜레이 + 일시정지/정지 확인
            if i < total - 1:
                should_stop = _check_controls(
                    pause_event, stop_event, random.uniform(0.05, 0.15)
                )
                if should_stop:
                    break


# === 내부 유틸리티 함수 ===


def _parse_naver_json(text: str) -> dict:
    """네이버 API 응답에서 )]}' 프리픽스를 제거하고 JSON 파싱"""
    cleaned = re.sub(r"^\)\]\}',?\s*\n?", "", text)
    return json.loads(cleaned)


def _strip_html(text: str) -> str:
    """HTML 태그 제거"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _format_timestamp(ts: int) -> str:
    """밀리초 타임스탬프를 YYYY.MM.DD 형식으로 변환"""
    if ts == 0:
        return ""
    from datetime import datetime

    dt = datetime.fromtimestamp(ts / 1000)
    return dt.strftime("%Y.%m.%d")


def _extract_content(frame) -> str:
    """게시물 본문 텍스트 추출 (SE3 또는 레거시)"""
    try:
        # SE3 (최신 에디터)
        el = frame.query_selector(".se-main-container")
        if el:
            return el.inner_text().strip()

        # 레거시 postViewArea
        el = frame.query_selector("#postViewArea")
        if el:
            return el.inner_text().strip()

        # 기타 컨테이너
        el = frame.query_selector("#post-view")
        if el:
            return el.inner_text().strip()

        # 최종 폴백: 전체 body 텍스트 중 주요 부분
        el = frame.query_selector(".se_component_wrap")
        if el:
            return el.inner_text().strip()

        return "[본문 추출 실패]"
    except Exception:
        return "[본문 추출 실패]"


def _extract_likes(frame) -> int:
    """좋아요(공감) 수 추출"""
    try:
        # 1순위: 공감 리스트 카운트 — 실제 네이버 블로그 DOM에서 확인된 셀렉터
        el = frame.query_selector("span.u_likeit_list_count._count")
        if el:
            text = el.inner_text().strip()
            if text.isdigit():
                return int(text)

        # 2순위: 공감 합계 텍스트 (일부 블로그 스킨)
        el = frame.query_selector("span.u_likeit_text._count")
        if el:
            text = el.inner_text().strip()
            if text.isdigit():
                return int(text)

        # 3순위: 구버전 sympathyCount
        el = frame.query_selector("#sympathyCount")
        if el:
            text = el.inner_text().strip()
            if text.isdigit():
                return int(text)

        # 4순위: 모든 공감 카운트 합산 (여러 리액션이 있는 경우)
        elements = frame.query_selector_all("span.u_likeit_list_count._count")
        if elements:
            total = 0
            for elem in elements:
                text = elem.inner_text().strip()
                if text.isdigit():
                    total += int(text)
            if total > 0:
                return total

        return 0
    except Exception:
        return 0


def _extract_comments(frame) -> int:
    """댓글 수 추출"""
    try:
        # 1순위: floating_bottom_commentCount — 실제 네이버 블로그 DOM에서 확인된 셀렉터
        el = frame.query_selector("#floating_bottom_commentCount")
        if el:
            text = el.inner_text().strip()
            if text.isdigit():
                return int(text)

        # 2순위: a.btn_comment 에서 "댓글 N" 추출
        el = frame.query_selector("a.btn_comment")
        if el:
            text = el.inner_text().strip()
            match = re.search(r"댓글\s*(\d+)", text)
            if match:
                return int(match.group(1))

        # 3순위: span.comment_wrap 에서 추출
        el = frame.query_selector("span.comment_wrap")
        if el:
            text = el.inner_text().strip()
            match = re.search(r"댓글\s*(\d+)", text)
            if match:
                return int(match.group(1))

        # 4순위: 모든 요소에서 "댓글 N" 패턴 탐색
        elements = frame.query_selector_all("a, button, span")
        for elem in elements:
            text = elem.inner_text().strip()
            match = re.search(r"댓글\s*(\d+)", text)
            if match:
                return int(match.group(1))

        return 0
    except Exception:
        return 0
