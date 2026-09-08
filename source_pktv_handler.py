import html
import re
import traceback
import zlib
import requests
import json
from datetime import datetime
import os
import yaml
from urllib.parse import urlencode, urlparse, parse_qs

from flask import Response, redirect
from tool import ToolUtil

from .setup import *


class PKTV_Handler:
    SOURCES = "POPKONTV"
    CHANNELS = []
    LAST_ERROR = None
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    CLIENT_KEY = "Client FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u"
    DEFAULT_HEADER = {
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Origin": "https://www.popkontv.com",
        "User-Agent": USER_AGENT,
        "ClientKey": CLIENT_KEY,
    }

    @classmethod
    def call_request(
        cls, http_method, url, payload=None, params=None, headers=None, cookies=None, redirects=False, proxies=None, stream=None, verify=None, json_data=None, timeout=15
    ):
        updated_headers = cls.DEFAULT_HEADER.copy()
        if headers:
            updated_headers.update(headers)
        if proxies:
            updated_headers["Connection"] = "close"

        for attempt in range(2):
            try:
                if http_method == "GET":
                    response = requests.get(
                        url,
                        params=params,
                        headers=updated_headers,
                        cookies=cookies,
                        allow_redirects=redirects,
                        proxies=proxies,
                        stream=stream,
                        verify=verify,
                        timeout=timeout,
                    )
                elif http_method == "GET_NO_DEFAULT":
                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        cookies=cookies,
                        allow_redirects=redirects,
                        proxies=proxies,
                        stream=stream,
                        verify=verify,
                        timeout=timeout,
                    )
                elif http_method == "POST":
                    response = requests.post(
                        url,
                        data=payload,
                        json=json_data,
                        params=params,
                        headers=updated_headers,
                        cookies=cookies,
                        allow_redirects=redirects,
                        proxies=proxies,
                        stream=stream,
                        verify=verify,
                        timeout=timeout,
                    )
                return response
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt == 0:
                    import time
                    time.sleep(0.5)
                    continue
                raise

    @classmethod
    def parse_token(cls, token):
        if not token:
            return {}
        if isinstance(token, dict):
            return token
        try:
            return json.loads(token)
        except Exception:
            return {"token": str(token)}

    @classmethod
    def login(cls, username, password):
        if not username or not password:
            return None

        proxies = None
        if P.ModelSetting.get_bool("use_proxy"):
            proxies = {
                "http": P.ModelSetting.get("proxy_url"),
                "https": P.ModelSetting.get("proxy_url"),
            }

        url = "https://www.popkontv.com/api/proxy/member/v1/login"
        headers = {
            "Content-Type": "application/json",
            "Authorization": cls.CLIENT_KEY.replace("Client", "Basic"),
            "Referer": "https://www.popkontv.com/login",
        }
        payload = {
            "partnerCode": "P-00001",
            "signId": username,
            "signPwd": password,
        }

        try:
            response = cls.call_request("POST", url, json_data=payload, headers=headers, proxies=proxies)
            if response.status_code == 200:
                data = response.json()
                if data.get("statusCd") == "S2000" and data.get("data"):
                    user_data = data["data"]
                    P.logger.info(f"PopkonTV 로그인 성공: {user_data.get('nickName')} ({user_data.get('signId')})")
                    return json.dumps(user_data)
                else:
                    P.logger.error(f"PopkonTV 로그인 실패: {data.get('statusMsg')}")
                    return None
            else:
                P.logger.error(f"PopkonTV 로그인 HTTP 오류: {response.status_code}")
                return None
        except Exception as e:
            P.logger.error(f"PopkonTV 로그인 예외: {str(e)}")
            P.logger.error(traceback.format_exc())
            return None

    @classmethod
    def get_list_data(cls, token):
        proxies = None
        if P.ModelSetting.get_bool("use_proxy"):
            proxies = {
                "http": P.ModelSetting.get("proxy_url"),
                "https": P.ModelSetting.get("proxy_url"),
            }

        url = "https://www.popkontv.com/api/proxy/broadcast/v3.1/livelist"
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://www.popkontv.com/live-more",
        }
        user_info = cls.parse_token(token)
        if user_info.get("token"):
            headers["Authorization"] = f"Bearer {user_info['token']}"

        all_channels = []
        page = 1
        page_size = 100
        while True:
            payload = {
                "castListTarget": 0,
                "main": False,
                "pageNum": page,
                "pageSize": page_size,
                "partnerCode": user_info.get("partnerCode", "P-00001"),
                "signId": user_info.get("signId", ""),
                "sortType": 0,
                "chrFanPchrgBrdcExpyn": True,
            }
            try:
                response = cls.call_request("POST", url, json_data=payload, headers=headers, proxies=proxies)
                if response.status_code == 200:
                    res_data = response.json()
                    if res_data.get("statusCd") != "S2000":
                        break
                    items = res_data.get("data", {}).get("list", [])
                    if not items:
                        break
                    all_channels.extend(items)
                    if len(items) < page_size or page >= 5:
                        break
                    page += 1
                elif response.status_code in (400, 401) and "Authorization" in headers:
                    P.logger.warning(f"PopkonTV 토큰 오류({response.status_code}), 게스트 모드로 목록 재시도")
                    del headers["Authorization"]
                    payload["signId"] = ""
                    continue
                else:
                    P.logger.error(f"PopkonTV livelist HTTP 오류: {response.status_code}")
                    break
            except Exception as e:
                P.logger.error(f"PopkonTV 방송 목록 조회 예외: {str(e)}")
                if "Authorization" in headers:
                    P.logger.warning("PopkonTV 방송 목록 조회 예외 발생으로 게스트 모드 1회 재시도")
                    del headers["Authorization"]
                    payload["signId"] = ""
                    continue
                break

        return all_channels

    @classmethod
    def ch_list(cls, token):
        cls.CHANNELS = []
        items = cls.get_list_data(token)

        for idx, item in enumerate(items):
            sign_id = item.get("signId", "")
            cast_partner_code = item.get("partnerCode", "P-00001")

            # Use authoritative session start date from pkCastCode
            pk_cast_code = item.get("pkCastCode", "")
            if pk_cast_code and "-" in pk_cast_code:
                cast_start_date = pk_cast_code.split("-", 1)[1]
            else:
                cast_start_date = item.get("castStartDateCode", "")

            title = (item.get("castTitle") or "").strip()
            nickname = (item.get("nickName") or "").strip()
            count = item.get("watchCnt", 0)
            is_adult = item.get("isAdult") == 1
            is_pay = item.get("pay") == 1
            is_fan = item.get("isFan") == 1
            cast_type = str(item.get("castType", 0))
            logo = item.get("pfileName") or item.get("onErrorImg") or ""

            icon = []
            if is_adult:
                icon.append("성인")
            if is_pay:
                icon.append("유료")
            if is_fan:
                icon.append("팬")

            if icon:
                current = f"[{' '.join(icon)}] {title} [{count}명]"
            else:
                current = f"{title} [{count}명]"

            ch_num = item.get("castListNum") or (idx + 1)

            cls.CHANNELS.append(
                {
                    "source": cls.SOURCES,
                    "id": str(ch_num),
                    "cast_id": sign_id,
                    "cast_partner_code": cast_partner_code,
                    "cast_start_date": str(cast_start_date),
                    "cast_type": cast_type,
                    "logo": logo,
                    "channel": nickname.replace(",", "."),
                    "current": current.replace(",", "."),
                    "url": ToolUtil.make_apikey_url(
                        f"/{P.package_name}/api/url.m3u8?cast_id={sign_id}&cast_partner_code={cast_partner_code}&cast_start_date={cast_start_date}"
                    ),
                }
            )

        return cls.CHANNELS

    @classmethod
    def get_live_view(cls, cast_id, cast_partner_code, token, web_list_model=None, cast_start_date=None):
        proxies = None
        if P.ModelSetting.get_bool("use_proxy"):
            proxies = {
                "http": P.ModelSetting.get("proxy_url"),
                "https": P.ModelSetting.get("proxy_url"),
            }

        user_info = cls.parse_token(token)
        user_token = user_info.get("token")

        cls.LAST_ERROR = None
        cast_type = "0"

        # Check cached channel list first
        cached = [c for c in (cls.CHANNELS or []) if c.get("cast_id") == cast_id]
        if cached:
            ch_info = cached[0]
            if not cast_start_date:
                cast_start_date = ch_info.get("cast_start_date")
            cast_partner_code = cast_partner_code or ch_info.get("cast_partner_code")
            cast_type = ch_info.get("cast_type", "0")

        # If still missing start date, fetch from livelist
        if not cast_start_date:
            items = cls.get_list_data(token)
            for it in items:
                if it.get("signId") == cast_id:
                    pk = it.get("pkCastCode", "")
                    if pk and "-" in pk:
                        cast_start_date = pk.split("-", 1)[1]
                    else:
                        cast_start_date = it.get("castStartDateCode", "")
                    cast_partner_code = it.get("partnerCode", cast_partner_code)
                    cast_type = str(it.get("castType", 0))
                    break

        if not cast_start_date:
            cls.LAST_ERROR = f"방송 시작 정보를 찾을 수 없습니다: cast_id={cast_id}"
            P.logger.error(cls.LAST_ERROR)
            return None

        headers = {
            "Content-Type": "application/json",
            "Referer": "https://www.popkontv.com/live-more",
        }

        # Try requesting watch stream (retry once with fresh livelist if E5: broadcast desynchronized/restarted)
        for attempt in range(2):
            cast_code = f"{cast_id}-{cast_start_date}"

            if user_token:
                watch_url = "https://www.popkontv.com/api/proxy/broadcast/v1/castwatchonoff"
                headers["Authorization"] = f"Bearer {user_token}"
                payload = {
                    "androidStore": 0,
                    "castCode": cast_code,
                    "castPartnerCode": cast_partner_code or "P-00001",
                    "castSignId": cast_id,
                    "castType": cast_type,
                    "commandType": 0,
                    "exePath": 0,
                    "isSecret": 0,
                    "partnerCode": user_info.get("partnerCode", "P-00001"),
                    "password": "",
                    "signId": user_info.get("signId", ""),
                    "version": "4.6.2",
                }
            else:
                watch_url = "https://www.popkontv.com/api/proxy/broadcast/v1/castwatchonoffguest"
                payload = {
                    "androidStore": 0,
                    "castCode": cast_code,
                    "castPartnerCode": cast_partner_code or "P-00001",
                    "castSignId": cast_id,
                    "castType": cast_type,
                    "commandType": 0,
                    "exePath": 0,
                    "partnerCode": "P-00001",
                    "password": "",
                    "version": "4.6.2",
                }

            try:
                response = cls.call_request("POST", watch_url, json_data=payload, headers=headers, proxies=proxies)
                if response.status_code == 200:
                    res = response.json()
                    if res.get("statusCd") in ("L0000", "S2000"):
                        cast_hls_url = res.get("data", {}).get("castHlsUrl")
                        if not cast_hls_url:
                            cls.LAST_ERROR = "PopkonTV HLS URL 없음"
                            P.logger.error(f"{cls.LAST_ERROR}: {res}")
                            return None

                        # Resolve master playlist into chunklist m3u8
                        m3u8_url = cast_hls_url
                        try:
                            r_m3u8 = cls.call_request("GET_NO_DEFAULT", cast_hls_url, headers={"User-Agent": cls.USER_AGENT}, proxies=proxies)
                            if r_m3u8.status_code == 200:
                                lines = r_m3u8.text.splitlines()
                                for line in lines:
                                    line = line.strip()
                                    if line.startswith("chunklist"):
                                        base_url = cast_hls_url[: cast_hls_url.rfind("/") + 1]
                                        m3u8_url = f"{base_url}{line}"
                                        break
                        except Exception as e:
                            P.logger.error(f"chunklist 해석 오류: {str(e)}")

                        ############# DB ##############
                        if web_list_model:
                            try:
                                cached_ch = [x for x in (cls.CHANNELS or []) if x.get("cast_id") == cast_id]
                                if cached_ch:
                                    channel_item = cached_ch[0]
                                    db_item = web_list_model()
                                    db_item.url = m3u8_url
                                    try:
                                        db_item.ch_id = int(channel_item["id"])
                                    except Exception:
                                        db_item.ch_id = abs(hash(cast_id)) % 100000000
                                    db_item.current = channel_item["current"]
                                    db_item.channel = channel_item["channel"]
                                    db_item.save()
                            except Exception as db_e:
                                P.logger.error(f"DB 저장 예외: {str(db_e)}")
                        ############# DB ##############

                        return m3u8_url

                    err_code = res.get("statusCd", "")
                    data_err = res.get("data", {}).get("errorCode", "")

                    # If E5 on first attempt, refresh from livelist and retry
                    if attempt == 0 and (err_code == "L0001" and data_err == "E5"):
                        items = cls.get_list_data(token)
                        found = False
                        for it in items:
                            if it.get("signId") == cast_id:
                                pk = it.get("pkCastCode", "")
                                if pk and "-" in pk:
                                    cast_start_date = pk.split("-", 1)[1]
                                else:
                                    cast_start_date = it.get("castStartDateCode", "")
                                cast_partner_code = it.get("partnerCode", cast_partner_code)
                                cast_type = str(it.get("castType", 0))
                                found = True
                                break
                        if found:
                            continue

                    err_msg = res.get("statusMsg", "방송 시청 요청 실패")
                    if err_code == "L0001":
                        if "로그인" in err_msg:
                            err_msg = "성인 방송은 로그인이 필요합니다. [설정] 메뉴에서 성인인증된 팝콘TV 계정을 입력해주세요."
                        elif data_err == "E5":
                            err_msg = "방송이 종료되었거나 존재하지 않습니다."
                        else:
                            err_msg = f"방송 시청 불가 ({err_msg})"
                    elif err_code == "L0002":
                        err_msg = "비공개(비밀번호) 방송입니다."
                    elif err_code == "L0003":
                        err_msg = "팬클럽 전용 방송입니다."
                    elif err_code == "L0004":
                        err_msg = "유료 결제 방송입니다."
                    cls.LAST_ERROR = err_msg
                    P.logger.error(f"PopkonTV 방송 시청 요청 실패: {err_msg} (code: {err_code})")
                    return None
                else:
                    P.logger.error(f"방송 시청 API HTTP 오류: {response.status_code}")
                    return None
            except Exception as e:
                P.logger.error(f"get_live_view 예외: {str(e)}")
                P.logger.error(traceback.format_exc())
                return None

    @classmethod
    def url_m3u8(cls, req, token, web_list_model):
        streaming_type = P.ModelSetting.get("streaming_type")

        cast_id = req.args.get("cast_id")
        cast_partner_code = req.args.get("cast_partner_code")
        cast_start_date = req.args.get("cast_start_date")

        m3u8_url = cls.get_live_view(cast_id, cast_partner_code, token, web_list_model, cast_start_date=cast_start_date)

        if not m3u8_url:
            return Response("Broadcast not available", status=404)

        if streaming_type == "redirect":
            return redirect(m3u8_url, code=302)
        else:
            m3u8_url = cls.compress_text(m3u8_url)
            return_url = ToolUtil.make_apikey_url(f"/{P.package_name}/api/play?streaming_type={streaming_type}&url={m3u8_url}")
            return redirect(return_url, code=302)

    @classmethod
    def play(cls, req):
        streaming_type = req.args.get("streaming_type")
        url = cls.decompress_text(req.args.get("url"))
        proxies = None
        if P.ModelSetting.get_bool("use_proxy2"):
            proxies = {
                "http": P.ModelSetting.get("proxy_url"),
                "https": P.ModelSetting.get("proxy_url"),
            }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "User-Agent": cls.USER_AGENT,
        }
        response = cls.call_request(
            "GET_NO_DEFAULT", url, payload=None, params=None, headers=headers, cookies=None, redirects=False, proxies=proxies
        )

        if response.status_code == 200:
            lines = response.text.splitlines()
            new_data = []
            for line in lines:
                line = line.strip()
                if line.strip() and not line.startswith("#EXT"):
                    if streaming_type == "proxy":
                        line = cls.compress_text(cls.resolve_relative_url(url, line))
                        new_line = ToolUtil.make_apikey_url(f"/{P.package_name}/api/segment?ts={line}")
                        new_data.append(new_line)
                    elif streaming_type == "direct":
                        new_line = cls.resolve_relative_url(url, line)
                        new_data.append(new_line)
                else:
                    new_data.append(line)

            data = "\n".join(new_data)
            return Response(data, content_type="application/vnd.apple.mpegurl")

        return Response("Error loading stream", status=500)

    @classmethod
    def segment(cls, req):
        proxies = None
        if P.ModelSetting.get_bool("use_proxy2"):
            proxies = {
                "http": P.ModelSetting.get("proxy_url"),
                "https": P.ModelSetting.get("proxy_url"),
            }
        url = cls.decompress_text(req.args.get("ts"))
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "User-Agent": cls.USER_AGENT,
        }
        response = cls.call_request("GET_NO_DEFAULT", url, headers=headers, proxies=proxies, stream=True, verify=False)
        return Response(response.iter_content(chunk_size=1048576), response.status_code, content_type="video/MP2T", direct_passthrough=True)

    @staticmethod
    def resolve_relative_url(base_url, relative_url):
        if relative_url.startswith("http"):
            return relative_url

        base_parts = base_url.split("/")[:-1]
        relative_parts = relative_url.split("/")

        for part in relative_parts:
            if part == "..":
                base_parts.pop()
            else:
                base_parts.append(part)

        return "/".join(base_parts)

    @staticmethod
    def decompress_text(compressed_text):
        compressed_data = bytes.fromhex(compressed_text)
        data = zlib.decompress(compressed_data)
        text = data.decode("utf-8")
        return text

    @staticmethod
    def compress_text(text):
        data = text.encode("utf-8")
        compressed_data = zlib.compress(data)
        compressed_text = compressed_data.hex()
        return compressed_text

    @classmethod
    def make_m3u(cls, token):
        M3U_FORMAT = '#EXTINF:-1 tvg-id="{id}" tvg-name="{title}" tvg-logo="{logo}" group-title="{group}" tvg-chno="{ch_no}" tvh-chnum="{ch_no}",{title}\n{url}\n'
        m3u = "#EXTM3U\n"
        for idx, item in enumerate(cls.ch_list(token)):
            m3u += M3U_FORMAT.format(
                id=f"{item['id']}",
                title=f"{item['current']} ({item['channel']})",
                group=item["source"],
                ch_no=str(idx + 1),
                url=item["url"],
                logo=item["logo"],
            )
        return Response(m3u, headers={"Content-Type": "text/plain; charset=utf-8"})

    @classmethod
    def make_playlist(cls, playlist):
        last_10_items = playlist.query.order_by(playlist.id.desc()).limit(10).all()

        M3U_FORMAT = '#EXTINF:-1 tvg-id="{id}" tvg-name="{title}" tvg-logo="{logo}" group-title="{group}" tvg-chno="{ch_no}" tvh-chnum="{ch_no}",{title}\n{url}\n'
        m3u = "#EXTM3U\n"
        for idx, item in enumerate(last_10_items):
            m3u += M3U_FORMAT.format(
                id=f"{item.ch_id}",
                title=f"{item.current} ({item.channel})",
                group="list",
                ch_no=str(idx + 1),
                url=item.url,
                logo="",
            )
        return Response(m3u, headers={"Content-Type": "text/plain; charset=utf-8"})

    @classmethod
    def make_yaml(cls, token):
        data = {
            "primary": True,
            "code": f"{cls.SOURCES.lower()}",
            "title": f"[{cls.SOURCES}]",
            "year": f"{datetime.now().year}",
            "genres": "Live",
            "posters": "https://cdn.discordapp.com/attachments/877784202651787316/1137634131799453716/popkontv.png",
            "summary": "",
            "extras": [],
        }

        playlist = cls.ch_list(token)

        if not playlist:
            data["extras"].append(
                {
                    "mode": "mp4",
                    "type": "featurette",
                    "param": "https://cdn.discordapp.com/attachments/877784202651787316/1128156544421343292/1.mp4",
                    "title": "방송중인 채널이 없습니다.",
                    "thumb": "https://media.discordapp.net/attachments/973582802102648882/1006128472856465458/unknown.png",
                }
            )
        else:
            for idx, item in enumerate(playlist):
                data["extras"].append(
                    {
                        "mode": "m3u8",
                        "type": "featurette",
                        "param": item["url"],
                        "title": f"{item['current'].replace(',','')} ({item['channel'].replace(',','')})",
                        "thumb": item["logo"],
                    }
                )

        yaml_data = yaml.dump(data, allow_unicode=True, sort_keys=False, encoding="utf-8")
        return Response(yaml_data, headers={"Content-Type": "text/yaml; charset=utf-8"})

    @classmethod
    def plex_refresh_by_item(cls, item_id):
        try:
            plex_server_url = P.ModelSetting.get("plex_server_url")
            plex_token = P.ModelSetting.get("plex_token")

            url = f"{plex_server_url}/library/metadata/{item_id}/refresh?X-Plex-Token={plex_token}"
            ret = requests.put(url, timeout=10)
            ret.raise_for_status()

            P.logger.debug("Plex 메타 데이터 새로고침이 성공적으로 시작되었습니다.")
        except Exception as e:
            P.logger.error(f"Exception:{str(e)}")
            P.logger.error(traceback.format_exc())

    @classmethod
    def sync_yaml_data(cls):
        try:
            yaml_url = ToolUtil.make_apikey_url(f"/{P.package_name}/api/yaml")
            local_path = P.ModelSetting.get("yaml_path")

            P.logger.debug(f"yaml_url:{yaml_url}")
            response = requests.get(yaml_url, timeout=10)
            new_data = yaml.safe_load(response.content)
            previous_data = yaml.safe_load(open(local_path, encoding="utf-8")) if os.path.exists(local_path) else None

            new_data_extras_data = new_data["extras"]
            previous_extras_data = previous_data["extras"]

            if previous_extras_data is not None and previous_extras_data != new_data_extras_data:
                updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_data["summary"] = f"마지막 업데이트 시간 : {updated_at}"

                with open(local_path, "w", encoding="utf-8") as file:
                    yaml.dump(
                        new_data,
                        file,
                        allow_unicode=True,
                        sort_keys=False,
                        encoding="utf-8",
                    )
                    P.logger.debug("데이터가 변경되어 로컬에 저장되었습니다.")
        except Exception as e:
            P.logger.error(f"Exception:{str(e)}")
            P.logger.error(traceback.format_exc())
