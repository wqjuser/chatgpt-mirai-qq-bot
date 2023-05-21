import hashlib
from typing import List, Any
import base64
import httpx
import requests
from graia.ariadne.message.element import Image

from constants import config
from .base import DrawingAPI
import aiohttp
import ctypes
from graia.ariadne.message.element import Image as GraiaImage
hashu = lambda word: ctypes.c_uint64(hash(word)).value


def basic_auth_encode(authorization: str) -> str:
    authorization_bytes = authorization.encode('utf-8')
    encoded_authorization = base64.b64encode(authorization_bytes).decode('utf-8')
    return f"Basic {encoded_authorization}"


def init_authorization():
    if config.sdwebui.authorization != '':
        return basic_auth_encode(config.sdwebui.authorization)
    else:
        return ''


# analyzing parameters by imitating mj
def parse_args(args_str, default=None):
    arg_dict = {}
    arg_name = None
    arg_values = []
    if args_str != "":
        for arg in args_str.split():
            if arg.startswith("--"):
                if arg_name is not None:
                    if len(arg_values) == 1:
                        arg_dict[arg_name] = arg_values[0]
                    elif len(arg_values) > 1:
                        arg_dict[arg_name] = arg_values[0:]
                    else:
                        arg_dict[arg_name] = default
                arg_name = arg.lstrip("-")
                arg_values = []
            else:
                arg_values.append(arg)

        if arg_name is not None:
            if len(arg_values) == 1:
                arg_dict[arg_name] = arg_values[0]
            elif len(arg_values) > 1:
                arg_dict[arg_name] = arg_values[0:]
            else:
                arg_dict[arg_name] = default

    return arg_dict

    # deal with args


def deal_with_args(parsed_args):
    # deal with args
    width = 512
    height = 512
    pm = False
    if bool(parsed_args):
        if 'ar' in parsed_args:
            ar_value = parsed_args.get('ar')
            if ar_value == '1:1':
                width = 512
                height = 512
            if ar_value == '3:4':
                width = 768
                height = 1024
            if ar_value == '4:3':
                width = 1024
                height = 768
            if ar_value == '9:16':
                width = 576
                height = 1024
            if ar_value == '16:9':
                width = 1024
                height = 576
        if 'pm' in parsed_args:
            pm = True

    return width, height, pm


class SDWebUI(DrawingAPI):

    def __init__(self):
        self.baidu_api_key = None
        self.deepl_api_key = None
        self.baidu_secret_key = None
        self.api_info = None
        self.client = httpx.AsyncClient()
        self.headers = {
            "Authorization": f"{init_authorization()}"
        }

    async def text_to_img(self, prompt):
        if '--L' not in prompt:
            payload = {
                'enable_hr': 'false',
                'denoising_strength': 0.45,
                'prompt': f'{config.sdwebui.prompt_prefix}, {prompt}',
                'steps': 15,
                'seed': -1,
                'batch_size': 1,
                'n_iter': 1,
                'cfg_scale': 7.5,
                'restore_faces': 'false',
                'tiling': 'false',
                'script_name': f'{config.sdwebui.script_name}',
                'script_args': [f'{prompt}'],
                'negative_prompt': config.sdwebui.negative_prompt,
                'eta': 0,
                'sampler_name': config.sdwebui.sampler_index
            }

            for key, value in config.sdwebui.dict(exclude_none=True).items():
                if isinstance(value, bool):
                    payload[key] = 'true' if value else 'false'
                else:
                    payload[key] = value

            if '--real-c' in prompt:
                option_payload = {
                    "sd_model_checkpoint": "chilloutmix.safetensors",
                }
                response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                    f"{config.sdwebui.api_url}sdapi/v1/options",
                    json=option_payload, headers=self.headers)
            else:
                option_payload = {
                    "sd_model_checkpoint": "meinamix_v9.safetensors",
                }
                response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                    f"{config.sdwebui.api_url}sdapi/v1/options",
                    json=option_payload, headers=self.headers)

            resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                f"{config.sdwebui.api_url}sdapi/v1/txt2img",
                json=payload, headers=self.headers)
            resp.raise_for_status()
            r = resp.json()
            return [Image(base64=i) for i in r.get('images', [])]
        else:
            parsed_args = {}
            scene = prompt
            image_number = 1
            width = 512
            height = 512
            pm = False
            if scene != "":
                parsed_args = parse_args(scene)
                width_p, height_p, pm_p = deal_with_args(parsed_args)
                width = width_p
                height = height_p
                pm = pm_p
                index = scene.find("--")
                if index != -1:
                    scene = scene[:index]
            if bool(parsed_args):
                if 'pics' in parsed_args:
                    image_number = int(parsed_args.get('pics'))
            url = "https://cloud.leonardo.ai/api/rest/v1/generations"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "Authorization": "Bearer f9104f8f-7083-4c1b-9acf-39011244092f"
            }
            # 翻译用户提问为英文
        translated_prompt = await self.translate_with_deepl(scene, "zh", "en")
        if translated_prompt is None:
            translated_prompt = await self.translate_with_baidu(scene, "zh", "en")
        if translated_prompt is None:
            translated_prompt = scene
            payload = {
                "prompt": translated_prompt,
                "modelId": "d2fb9cf9-7999-4ae5-8bfe-f0df2d32abf8",
                "width": width,
                "height": height,
                "negative_prompt": config.sdwebui.negative_prompt,
                "num_inference_steps": 30,
                "promptMagic": True if pm else False,
                "num_images": image_number,
                "public": False,
                "tiling": False,
                "guidance_scale": 7
            }
            print("莱奥纳多的入参是：", f"{payload}")
            response = requests.post(url, json=payload, headers=headers)
            # response.raise_for_status()
            # r = response.json()
            print("莱奥纳多的返回值是：", f"{response.text}")
            return []
            # if response.status_code==200:

    async def img_to_img(self, init_images: List[Image], prompt=''):
        payload = {
            'init_images': [x.base64 for x in init_images],
            'enable_hr': 'false',
            'denoising_strength': 0.45,
            'prompt': f'{config.sdwebui.prompt_prefix}, {prompt}',
            'steps': 15,
            'seed': -1,
            'batch_size': 1,
            'n_iter': 1,
            'cfg_scale': 7.5,
            'restore_faces': 'false',
            'tiling': 'false',
            'script_name': f'{config.sdwebui.script_name}',
            'script_args': [f'{prompt}'],
            'negative_prompt': config.sdwebui.negative_prompt,
            'eta': 0,
            'sampler_index': config.sdwebui.sampler_index,
            "filter_nsfw": 'true' if config.sdwebui.filter_nsfw else 'false',
        }

        for key, value in config.sdwebui.dict(exclude_none=True).items():
            if isinstance(value, bool):
                payload[key] = 'true' if value else 'false'
            else:
                payload[key] = value

        resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(f"{config.sdwebui.api_url}sdapi/v1/img2img",
                                                                            json=payload, headers=self.headers)
        resp.raise_for_status()
        r = resp.json()
        return [Image(base64=i) for i in r.get('images', [])]

    async def __download_image(self, url) -> GraiaImage:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, proxy=self.api_info.proxy) as resp:
                if resp.status == 200:
                    return GraiaImage(data_bytes=await resp.read())

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
