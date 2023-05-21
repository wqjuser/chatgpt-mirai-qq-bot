import ctypes
import hashlib
from typing import Generator, Any

from adapter.botservice import BotAdapter
from config import BardCookiePath
from constants import botManager
from exceptions import BotOperationNotSupportedException
from loguru import logger
import json
import httpx
from urllib.parse import quote

hashu = lambda word: ctypes.c_uint64(hash(word)).value


class BardAdapter(BotAdapter):
    account: BardCookiePath

    def __init__(self, session_id: str = ""):
        super().__init__(session_id)
        self.baidu_api_key = None
        self.baidu_secret_key = None
        self.deepl_api_key = None
        self.at = None
        self.session_id = session_id
        self.account = botManager.pick('bard-cookie')
        self.client = httpx.AsyncClient(proxies=self.account.proxy)
        self.bard_session_id = ""
        self.r = ""
        self.rc = ""
        self.headers = {
            "Cookie": self.account.cookie_content,
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9',
        }

    async def get_at_token(self):

        response = await self.client.get(
            "https://bard.google.com/?hl=en",
            timeout=30,
            headers=self.headers,
            follow_redirects=True,
        )
        self.at = quote(response.text.split('"SNlM0e":"')[1].split('","')[0])

    async def rollback(self):
        raise BotOperationNotSupportedException()

    async def on_reset(self):
        await self.client.aclose()
        self.client = httpx.AsyncClient(proxies=self.account.proxy)
        self.bard_session_id = ""
        self.r = ""
        self.rc = ""
        await self.get_at_token()

    async def ask(self, prompt: str) -> Generator[str, None, None]:
        if not self.at:
            await self.get_at_token()
        # 翻译用户提问为英文
        translated_prompt = await self.translate_with_deepl(prompt, "zh", "en")
        if translated_prompt is None:
            translated_prompt = await self.translate_with_baidu(prompt, "zh", "en")
        if translated_prompt is None:
            translated_prompt = prompt
        try:
            url = "https://bard.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
            content = quote(translated_prompt.replace('"', "'")).replace("%0A", "%5C%5Cn")
            # 奇怪的格式 [null,"[[\"\"],null,[\"\",\"\",\"\"]]"]
            raw_data = f"f.req=%5Bnull%2C%22%5B%5B%5C%22{content}%5C%22%5D%2Cnull%2C%5B%5C%22{self.bard_session_id}%5C%22%2C%5C%22{self.r}%5C%22%2C%5C%22{self.rc}%5C%22%5D%5D%22%5D&at={self.at}&"
            response = await self.client.post(
                url,
                timeout=30,
                headers=self.headers,
                content=raw_data,
            )
            if response.status_code != 200:
                logger.error(f"[Bard] 请求出现错误，状态码: {response.status_code}")
                logger.error(f"[Bard] {response.text}")
                raise Exception("Authentication failed")
            res = response.text.split("\n")
            for lines in res:
                if "wrb.fr" in lines:
                    data = json.loads(json.loads(lines)[0][2])
                    result = data[0][0]
                    self.bard_session_id = data[1][0]
                    self.r = data[1][1]  # 用于下一次请求, 这个位置是固定的
                    # self.rc = data[4][1][0]
                    for check in data:
                        if not check:
                            continue
                        try:
                            for element in [element for row in check for element in row]:
                                if "rc_" in element:
                                    self.rc = element
                                    break
                        except:
                            continue
                    translated_result = await self.translate_with_deepl(result, "en", "zh")
                    if translated_result is None:
                        translated_result = await self.translate_with_baidu(result, "en", "zh")
                    if translated_result is None:
                        translated_result = result
                    logger.debug(f"[Bard] {self.bard_session_id} - {self.r} - {self.rc} - {result}")
                    yield translated_result
                    break

        except Exception as e:
            logger.exception(e)
            yield "[Bard] 出现了些错误"
            await self.on_reset()
            return

    async def translate_with_baidu(self, text: str, from_lang: str, to_lang: str) -> Any | None:
        url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
        salt = str(hashu(text))
        self.baidu_api_key = '20230227001577503'
        self.baidu_secret_key = 'o9kxQADPCdFf56FHPCIv'
        sign_str = self.baidu_api_key + text + salt + self.baidu_secret_key  # don't forget to add the secret key
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        params = {
            "q": text,
            "from": from_lang,
            "to": to_lang,
            "appid": self.baidu_api_key,
            "salt": salt,
            "sign": sign,
        }
        response = await self.client.get(url, params=params)
        if response.status_code != 200:
            return None
        return response.json()['trans_result'][0]['dst']

    async def translate_with_deepl(self, text: str, from_lang: str, to_lang: str) -> Any | None:
        url = "https://api-free.deepl.com/v2/translate"
        self.deepl_api_key = '1e23ad70-40b4-7e97-4d08-2239d2e114a6:fx'
        headers = {"Authorization": "DeepL-Auth-Key " + self.deepl_api_key}
        data = {
            "text": text,
            "source_lang": from_lang,
            "target_lang": to_lang,
        }
        response = await self.client.post(url, headers=headers, data=data)
        if response.status_code != 200:
            return None
        return response.json()['translations'][0]['text']
