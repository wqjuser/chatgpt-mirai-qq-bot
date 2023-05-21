from typing import List
import base64
import httpx
from graia.ariadne.message.element import Image

from constants import config
from .base import DrawingAPI
from loguru import logger
import aiohttp

from graia.ariadne.message.element import Image as GraiaImage


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
        self.api_info = None
        self.headers = {
            "Authorization": f"{init_authorization()}"
        }

    async def text_to_img(self, prompt):
        images = []
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
            url = "https://cloud.leonardo.ai/api/rest/v1/generations/"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": "Bearer f9104f8f-7083-4c1b-9acf-39011244092f"
            }
            payload = {
                "prompt": scene,
                "modelId": "d2fb9cf9-7999-4ae5-8bfe-f0df2d32abf8",
                "width": width,
                "height": height,
                "negative_prompt": config.sdwebui.negative_prompt,
                "num_inference_steps": 30,
                "promptMagic": "true" if pm else "false",
                "num_images": image_number,
                "public": "false",
                "tiling": "false",
                "guidance_scale": 7
            }
            response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(url, json=payload, headers=headers)
            response.raise_for_status()
            r = response.json()
            logger.error("莱奥纳多的返回值是：", f"{r}")
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
