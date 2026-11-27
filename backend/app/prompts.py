from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from .config import APP_HOME

CUSTOM_PROMPTS_PATH = APP_HOME / "prompt_library.json"

NEGATIVE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "neg_universal",
        "title": "萬用高品質（綜合防崩）",
        "kind": "all",
        "tag": "萬用",
        "description": "適合大多數畫圖與影片模型，全面抑制低解析、模糊、浮水印與基本結構崩壞。",
        "prompt": "lowres, worst quality, low quality, normal quality, jpeg artifacts, blurry, out of focus, bad anatomy, bad proportions, deformed, mutated, watermark, signature, username, text, logo, cropped",
    },
    {
        "id": "neg_portrait_hands",
        "title": "人像防畸形（手指／五官修復）",
        "kind": "image",
        "tag": "人像",
        "description": "專治多指、少指、融手、五官不對稱與斷肢等人像常見問題。",
        "prompt": "bad anatomy, bad hands, mutated hands, extra fingers, missing fingers, fused fingers, too many fingers, extra limbs, missing legs, disconnected limbs, poorly drawn face, deformed eyes, asymmetrical eyes, cross-eyed, long neck, distorted body",
    },
    {
        "id": "neg_photoreal",
        "title": "寫實攝影（去塑膠感與 CG 味）",
        "kind": "image",
        "tag": "寫實",
        "description": "消除過度磨皮、塑膠假皮膚、3D 渲染味與動畫畫風干擾。",
        "prompt": "anime, cartoon, illustration, painting, 3d render, cgi, plastic skin, airbrushed, overly smooth skin, wax figure, oversaturated, artificial lighting, uncanny valley, doll-like, fake bokeh",
    },
    {
        "id": "neg_anime",
        "title": "動漫插畫（乾淨線條防 3D 混入）",
        "kind": "image",
        "tag": "動漫",
        "description": "保持日系賽璐璐與細緻插畫質感，避免畫面跑偏成寫實或粗糙草稿。",
        "prompt": "photorealistic, realistic, photo, 3d, render, cgi, messy lineart, sketchy, muddy colors, worst quality, low quality, bad proportions, extra fingers, text, watermark, monochrome, grayscale",
    },
    {
        "id": "neg_commercial",
        "title": "商業攝影（去字去浮水印去雜邊）",
        "kind": "image",
        "tag": "商業",
        "description": "確保產品圖與海報背景乾淨，不出現亂碼文字、商標、邊框或污漬。",
        "prompt": "text, watermark, logo, brand name, signature, stamp, border, frame, price tag, cluttered background, dust, scratches, noise, overexposed highlights, harsh lens flare",
    },
    {
        "id": "neg_architecture",
        "title": "建築空間（防透視與結構扭曲）",
        "kind": "image",
        "tag": "建築",
        "description": "避免門窗歪斜、線條彎曲、透視錯誤與不合理幾何結構。",
        "prompt": "warped lines, crooked walls, distorted perspective, impossible geometry, floating objects, asymmetrical windows, blurry textures, messy clutter, lowres, oversaturated",
    },
    {
        "id": "neg_video_flicker",
        "title": "影片專用（防閃爍／防融化變形）",
        "kind": "video",
        "tag": "影片防閃",
        "description": "針對 Wan2.2 / MiniMax-H3 等影片模型，降低畫面閃爍、材質沸騰與物體融化。",
        "prompt": "flickering, morphing, melting objects, liquid distortion, temporal artifacts, frame jitter, strobe effect, ghosting, blurry motion, deformed limbs, static frozen frame, low quality, watermark",
    },
    {
        "id": "neg_video_camera",
        "title": "影片運鏡穩定（防劇烈抖動與跳幀）",
        "kind": "video",
        "tag": "穩鏡",
        "description": "維持電影運鏡平順與背景穩定，減少畫面跳動或構圖崩潰。",
        "prompt": "shaky camera, erratic movement, sudden jump cut, frame drops, unstable background, warping architecture, dizzy spin, motion smear, compression artifacts, subtitles, text overlay",
    },
]

BUILTIN_PROMPTS: List[Dict[str, Any]] = [
    # ========== IMAGE: 人像寫真 ==========
    {
        "id": "img_portrait_editorial",
        "kind": "image",
        "category": "人像寫真",
        "title": "自然窗光編輯風肖像（Kodak Portra 400）",
        "ratio": "3:4",
        "prompt": "Candid editorial portrait of a 28-year-old East Asian artisan with expressive eyes and natural subtle freckles, looking slightly away from the camera. Soft natural window light from the left, gentle shadows, neutral warm studio backdrop, shallow depth of field. Shot on 85mm lens at f/1.4, Kodak Portra 400 film aesthetic, authentic skin pores and texture, unretouched.",
        "negative_prompt": "anime, cartoon, 3d render, cgi, plastic skin, airbrushed, bad anatomy, bad hands, deformed eyes, watermark, text",
        "tags": ["85mm", "膠片感", "寫實"],
    },
    {
        "id": "img_portrait_beach",
        "kind": "image",
        "category": "人像寫真",
        "title": "黃金時刻海邊電影人像",
        "ratio": "3:4",
        "prompt": "Full-body cinematic portrait of a young Asian woman in a flowing white linen sundress standing barefoot on a golden-hour beach, warm sunset rim light glowing through wind-swept hair, gentle ocean waves reflecting amber and pastel violet sky. Shot on 50mm f/1.8 lens, natural skin texture, crisp detail, realistic photography.",
        "negative_prompt": "bad anatomy, extra fingers, mutated hands, plastic skin, oversaturated, cgi, watermark, blurry, deformed body",
        "tags": ["日落", "全身", "電影光影"],
    },
    {
        "id": "img_portrait_cyber_rain",
        "kind": "image",
        "category": "人像寫真",
        "title": "霓虹雨夜街頭人像",
        "ratio": "9:16",
        "prompt": "Cinematic street portrait of a stylish young woman holding a transparent umbrella in a rain-soaked Taipei alley at night. Vivid cyan and warm magenta neon reflections on wet asphalt and raindrops, shallow depth of field with glowing bokeh lights behind her. Shot on Sony A7R V, 35mm f/1.4, moody atmospheric lighting, hyper-realistic photography.",
        "negative_prompt": "cartoon, anime, 3d render, plastic skin, bad hands, extra fingers, blurry face, distorted umbrella, watermark",
        "tags": ["雨夜", "霓虹", "街拍"],
    },
    {
        "id": "img_portrait_jp_airy",
        "kind": "image",
        "category": "人像寫真",
        "title": "日系清透空氣感少女寫真（Fujifilm Classic Chrome）",
        "ratio": "3:4",
        "prompt": "Japanese editorial film portrait of a 22-year-old Japanese woman standing by a sunlit seaside train crossing in Kamakura, wearing a soft ivory knit cardigan and pleated skirt, gentle ocean breeze lifting her dark chestnut hair, bright airy natural sunlight, subtle halation and pastel cyan shadows. Shot on Fujifilm GFX100 II, 80mm f/1.7, Classic Chrome film simulation, authentic delicate skin texture.",
        "negative_prompt": "3d render, cgi, plastic skin, heavy makeup, oversaturated, bad hands, extra fingers, deformed eyes, watermark",
        "tags": ["日系", "空氣感", "鎌倉"],
    },
    {
        "id": "img_portrait_kr_studio",
        "kind": "image",
        "category": "人像寫真",
        "title": "韓系高級雜誌棚拍人像（Seoul Editorial）",
        "ratio": "3:4",
        "prompt": "High-fashion Korean studio portrait of a refined 25-year-old Korean woman wearing an oversized tailored beige wool blazer and minimalist pearl earrings, sleek glossy dark hair, clean glass-skin editorial makeup, poised calm expression looking directly into the lens. Soft diffused Octabox studio key light with crisp catchlights in eyes, seamless warm stone backdrop, Hasselblad X2D 90mm f/2.5, Vogue Korea editorial style.",
        "negative_prompt": "anime, cartoon, cgi, wax skin, over-smoothed face, bad anatomy, bad hands, cluttered background, text, watermark",
        "tags": ["韓系", "雜誌棚拍", "高級感"],
    },
    {
        "id": "img_portrait_tw_jiufen",
        "kind": "image",
        "category": "人像寫真",
        "title": "台灣九份紅燈籠暮色膠片人像",
        "ratio": "3:4",
        "prompt": "Atmospheric cinematic film portrait of a 24-year-old Taiwanese woman standing on a misty stone stairway in Jiufen old street at blue hour, glowing red traditional paper lanterns illuminating her gentle smile and warm wool coat, distant ocean lights twinkling through mountain fog. Shot on Leica M11, 50mm f/1.4 Summilux, CineStill 800T halation glow, natural candid film grain.",
        "negative_prompt": "cgi, 3d render, plastic skin, bad hands, extra fingers, distorted lanterns, crowd clutter, watermark, text",
        "tags": ["台灣", "九份", "膠片暮色"],
    },
    {
        "id": "img_portrait_tw_campus",
        "kind": "image",
        "category": "人像寫真",
        "title": "清新校園林蔭大道午後人像",
        "ratio": "3:4",
        "prompt": "Fresh youthful portrait of a cheerful Taiwanese college girl in a crisp white cotton shirt and denim skirt holding a notebook along a sunlit banyan-tree campus walkway, dappled golden afternoon sunlight filtering through green leaves, warm candid laugh, natural hair strands catching rim light. 85mm f/1.4 creamy bokeh, authentic film color grading.",
        "negative_prompt": "anime, cgi, plastic skin, bad hands, extra fingers, distorted face, harsh shadows, watermark",
        "tags": ["清新", "校園", "自然光"],
    },
    {
        "id": "img_portrait_winter_snow",
        "kind": "image",
        "category": "人像寫真",
        "title": "北海道雪地毛衣溫柔特寫",
        "ratio": "3:4",
        "prompt": "Intimate winter close-up portrait of a young East Asian woman wrapped in a chunky cream cashmere scarf and knit sweater in gently falling snow in Hokkaido, delicate snowflakes resting on her eyelashes and dark hair, rosy cold-flushed cheeks, soft overcast snowy daylight creating luminous eyes. Shot on 85mm f/1.2, ultra-sharp natural skin texture.",
        "negative_prompt": "cgi, 3d, plastic skin, distorted eyes, bad hands, oversaturated, harsh flash, watermark",
        "tags": ["冬日雪景", "特寫", "日系"],
    },
    {
        "id": "img_portrait_male_bw",
        "kind": "image",
        "category": "人像寫真",
        "title": "都會型男黑白電影光影肖像",
        "ratio": "3:4",
        "prompt": "Dramatic monochrome film portrait of a 30-year-old East Asian man in a dark turtleneck and tailored wool overcoat standing near a rain-streaked glass window, sharp sculptural Rembrandt side lighting highlighting strong jawline and calm introspective gaze. Shot on Leica Monochrom 50mm f/1.4, rich silver gelatin black-and-white contrast, authentic film grain.",
        "negative_prompt": "color, cartoon, 3d render, plastic skin, deformed eyes, bad anatomy, watermark, text",
        "tags": ["男像", "黑白電影", "質感"],
    },

    # ========== IMAGE: 國風與古風人物 ==========
    {
        "id": "img_guofeng_tang",
        "kind": "image",
        "category": "國風人物",
        "title": "盛唐紅妝仕女宮燈夜宴",
        "ratio": "3:4",
        "prompt": "Exquisite cinematic portrait of a Tang Dynasty noblewoman wearing an intricate crimson and gold embroidered silk Qixiong Ruqun hanfu with flowing translucent gauze shawl, delicate floral Huadian forehead mark, ornate gold hairpin with dangling pearls, holding a round silk palace fan beside glowing carved wooden lanterns in a misty courtyard at night. Warm amber candlelight, museum-grade fabric weave detail, photorealistic cinema still.",
        "negative_prompt": "modern clothes, plastic jewelry, bad hands, extra fingers, mutated fan, cgi, low quality, text, watermark",
        "tags": ["唐風", "漢服", "宮燈"],
    },
    {
        "id": "img_guofeng_song_bamboo",
        "kind": "image",
        "category": "國風人物",
        "title": "宋韻青瓷素雅漢服竹林執扇",
        "ratio": "3:4",
        "prompt": "Poetic Song Dynasty style portrait of an elegant young Chinese woman dressed in a celadon-green and pearl-white silk Beizi hanfu standing gracefully inside a tranquil misty bamboo grove, holding an embroidered silk round fan. Soft morning mist and diffused emerald sunlight filtering through bamboo leaves, understated Song aesthetics, delicate authentic skin texture, 85mm f/1.8 fine-art photography.",
        "negative_prompt": "modern accessories, neon colors, plastic skin, bad hands, extra fingers, blurry face, cgi, watermark",
        "tags": ["宋風", "竹林", "素雅漢服"],
    },
    {
        "id": "img_guofeng_wuxia",
        "kind": "image",
        "category": "國風人物",
        "title": "江湖白衣劍客竹海飛雪（武俠電影感）",
        "ratio": "16:9",
        "prompt": "Epic Chinese wuxia cinema still of a poised young swordsman in flowing white and ink-gray layered martial arts robes standing on a snow-dusted stone bridge amid a towering emerald bamboo forest, right hand resting on the ornate hilt of a traditional Jian sword, wind sweeping snow petals and fabric across the frame. Dramatic moody overcast lighting, Zhang Yimou film color palette, 35mm anamorphic lens.",
        "negative_prompt": "modern clothes, western armor, deformed sword, bad hands, extra fingers, cartoon, 3d render, watermark",
        "tags": ["武俠", "劍客", "電影寬銀幕"],
    },
    {
        "id": "img_guofeng_dunhuang",
        "kind": "image",
        "category": "國風人物",
        "title": "敦煌飛天金箔壁畫仙女",
        "ratio": "9:16",
        "prompt": "Breathtaking ornate portrait of a celestial Dunhuang Feitian dancer floating gracefully amid drifting golden desert dust and glowing silk ribbons, wearing intricate lapis-lazuli, cinnabar red, and hammered gold filigree jewelry, delicate classical East Asian features, holding a carved wooden Pipa lute. Warm dramatic sunbeams illuminating floating incense smoke and mineral pigment tones, ultra-detailed fantasy fine art photography.",
        "negative_prompt": "modern items, plastic look, bad hands, extra fingers, deformed instrument, blurry, lowres, watermark",
        "tags": ["敦煌飛天", "金箔", "華麗國風"],
    },
    {
        "id": "img_guofeng_qipao",
        "kind": "image",
        "category": "國風人物",
        "title": "江南煙雨民國復古青花旗袍佳人",
        "ratio": "3:4",
        "prompt": "Nostalgic Republican-era portrait of a graceful Taiwanese-Chinese woman wearing a tailored emerald velvet and subtle floral silk Qipao, holding a classic oiled-paper umbrella while walking along a rain-glistening stone alley beside a misty Jiangnan canal. Soft reflection of warm lantern light on wet cobblestones, Wong Kar-wai cinema color palette, 50mm f/1.4 film photography.",
        "negative_prompt": "modern buildings, plastic skin, bad hands, extra fingers, deformed umbrella, cgi, oversaturated, watermark",
        "tags": ["旗袍", "江南煙雨", "復古電影"],
    },

    # ========== IMAGE: 動漫插畫 ==========
    {
        "id": "img_anime_ufotable",
        "kind": "image",
        "category": "動漫插畫",
        "title": "雨夜東京賽博法師（Ufotable 電影質感）",
        "ratio": "16:9",
        "prompt": "A cinematic anime film still of a young cyber-mage standing on a rain-drenched Tokyo rooftop at night, holding a glowing holographic rune staff. Moody neo-noir atmosphere, teal and magenta color palette, crisp cel-painted edges, fine crosshatching linework, dynamic wind-blown coat, dramatic volumetric neon glow and wet reflections, modern Ufotable animation production quality.",
        "negative_prompt": "photorealistic, 3d render, cgi, messy lineart, worst quality, low quality, bad proportions, extra fingers, text, watermark",
        "tags": ["賽博", "電影幀", "高精細"],
    },
    {
        "id": "img_anime_ghibli",
        "kind": "image",
        "category": "動漫插畫",
        "title": "吉卜力風格盛夏山城小鎮",
        "ratio": "16:9",
        "prompt": "Hand-painted Japanese anime background illustration of a cozy hillside European-inspired village in midsummer, terracotta roofs, blooming flower boxes, a small bakery overlooking an azure sea, towering fluffy cumulus clouds in a brilliant blue sky, warm nostalgic sunlight, rich gouache and watercolor brushwork, Studio Ghibli aesthetic.",
        "negative_prompt": "photorealistic, 3d, cgi, dark moody, muddy colors, lowres, text, watermark, blurry",
        "tags": ["治癒", "手繪水彩", "風景"],
    },
    {
        "id": "img_anime_shinkai",
        "kind": "image",
        "category": "動漫插畫",
        "title": "新海誠風格黃昏車站與流星雲海",
        "ratio": "16:9",
        "prompt": "Breathtaking anime scene of a quiet coastal train platform at twilight, a high school student looking up at a luminous twilight sky filled with dramatic golden-pink clouds, glowing contrails, and a streaking comet. Sparkling lens flare, intricate power lines and reflection on train glass, vibrant Makoto Shinkai cinematic lighting.",
        "negative_prompt": "photorealistic, 3d, cgi, blurry, low quality, dull colors, bad anatomy, watermark, text",
        "tags": ["黃昏", "光影", "青春"],
    },

    # ========== IMAGE: 商業攝影 ==========
    {
        "id": "img_prod_watch",
        "kind": "image",
        "category": "商業攝影",
        "title": "瑞士機械錶微距廣告攝影",
        "ratio": "1:1",
        "prompt": "Macro commercial photography of a luxury Swiss skeleton mechanical wristwatch resting on dark honed slate. Extreme close-up revealing intricate spinning brass gears, ruby jewel bearings, and brushed steel bevels. Warm tungsten side light creating golden highlights on polished metal, Canon MP-E 65mm macro lens at f/8, focus-stacked razor sharpness, horology magazine editorial style.",
        "negative_prompt": "text, watermark, logo, scratches, dust, blurry, plastic look, lowres, cluttered background",
        "tags": ["微距", "精品", "棚拍"],
    },
    {
        "id": "img_prod_perfume",
        "kind": "image",
        "category": "商業攝影",
        "title": "高訂香水玻璃水花商業大片",
        "ratio": "3:4",
        "prompt": "High-speed commercial studio photograph of a minimalist faceted crystal perfume bottle filled with amber liquid, suspended above a dark reflective water surface with a sculptural dynamic splash of crystal-clear water droplets frozen in mid-air. Soft rim lighting, champagne gold caustics, crisp luxury cosmetics campaign aesthetic, ultra-sharp 85mm studio shot.",
        "negative_prompt": "text, brand name, watermark, blurry splash, messy background, distorted bottle, low quality, noise",
        "tags": ["液體飛濺", "美妝", "廣告"],
    },
    {
        "id": "img_prod_ramen",
        "kind": "image",
        "category": "商業攝影",
        "title": "熱氣騰騰日式豚骨拉麵美食攝影",
        "ratio": "4:3",
        "prompt": "Appetizing editorial food photography of a steaming ceramic bowl of authentic Japanese tonkotsu ramen on a rustic charred-wood counter. Creamy rich broth, glossy charred chashu pork slices, molten soft-boiled ajitama egg, vibrant green scallions, nori sheet, rising delicate wisps of steam backlit by warm Izakaya lantern light. 50mm f/2.0 shallow depth of field.",
        "negative_prompt": "plastic food, unappetizing, artificial colors, blurry, text, watermark, cgi, oversaturated",
        "tags": ["美食", "熱氣", "暖光"],
    },

    # ========== IMAGE: 建築空間 ==========
    {
        "id": "img_arch_santorini",
        "kind": "image",
        "category": "建築空間",
        "title": "聖托里尼懸崖極簡無邊際別墅",
        "ratio": "16:9",
        "prompt": "Architectural visualization of a contemporary minimalist cliffside villa in Santorini, Greece. Clean white lime-washed cubic volumes carved into raw volcanic rock, infinity pool overflowing toward the Aegean caldera at golden hour. Dramatic amber and violet sky reflecting on glassy water, tilt-shift architectural lens perspective, matte concrete and travertine stone textures, photorealistic.",
        "negative_prompt": "warped lines, crooked walls, distorted perspective, impossible geometry, blurry textures, watermark, text, cartoon",
        "tags": ["建築", "移軸鏡頭", "極簡"],
    },
    {
        "id": "img_arch_interior",
        "kind": "image",
        "category": "建築空間",
        "title": "北歐侘寂風陽光原木客廳",
        "ratio": "16:9",
        "prompt": "Interior design photography of a serene Japandi living room with pale oak flooring, textured lime plaster walls, a low-profile oatmeal linen sofa, organic sculptural ceramic vases, and a large floor-to-ceiling window framing a quiet bamboo courtyard. Soft afternoon sunlight casting leafy shadows across the wall, Architectural Digest editorial style, natural color grading.",
        "negative_prompt": "warped furniture, messy clutter, artificial neon lighting, distorted perspective, lowres, cgi look, watermark",
        "tags": ["室內設計", "侘寂風", "自然光"],
    },
    {
        "id": "img_arch_kyoto",
        "kind": "image",
        "category": "建築空間",
        "title": "京都晨霧紅葉古寺庭園",
        "ratio": "3:4",
        "prompt": "Serene landscape photography of a historic wooden temple pavilion in Kyoto surrounded by glowing crimson Japanese maple trees reflected in a mirror-still koi pond. Gentle morning mist drifting through the garden, warm sunrise beams piercing the autumn foliage, mossy stepping stones, shot on medium format camera, ultra-detailed tranquil atmosphere.",
        "negative_prompt": "crowds, tourists, modern cars, electric wires, oversaturated, blurry, watermark, text",
        "tags": ["京都", "紅葉", "晨霧"],
    },

    # ========== IMAGE: 3D 與國風藝術 ==========
    {
        "id": "img_art_blindbox",
        "kind": "image",
        "category": "3D 與國風藝術",
        "title": "盲盒風格可愛 3D 太空小貓公仔",
        "ratio": "1:1",
        "prompt": "Adorable 3D collectible blind-box vinyl figurine of a chubby calico cat wearing a pastel mint retro astronaut helmet and tiny jetpack, floating playfully next to a glowing crescent moon. Matte PVC clay-like tactile material with subtle glossy visor reflections, soft studio three-point lighting, clean gradient lavender background, Octane Render, Pixar and Pop Mart aesthetic.",
        "negative_prompt": "ugly, deformed, rough geometry, low poly, noisy shadows, text, watermark, creepy eyes",
        "tags": ["盲盒", "可愛3D", "材質感"],
    },
    {
        "id": "img_art_guofeng",
        "kind": "image",
        "category": "3D 與國風藝術",
        "title": "宋代青綠山水潑墨仙境",
        "ratio": "16:9",
        "prompt": "Masterpiece traditional Chinese gongbi and splashed-ink landscape painting on aged silk scroll, inspired by Song Dynasty blue-green landscapes. Towering misty emerald and mineral-blue mountain peaks rising above drifting white clouds, delicate golden sunlight brushing pine ridges, a tiny lone wooden boat gliding across a tranquil river, refined brushwork and poetic negative space.",
        "negative_prompt": "modern buildings, photorealistic photo, 3d render, neon colors, messy smudges, western oil paint, watermark",
        "tags": ["青綠山水", "水墨", "東方美學"],
    },
    {
        "id": "img_art_isometric",
        "kind": "image",
        "category": "3D 與國風藝術",
        "title": "微縮等距視角深夜魔法書房",
        "ratio": "1:1",
        "prompt": "Highly detailed 3D isometric cutaway diorama of a cozy wizard's midnight study room floating on a dark backdrop. Floor-to-ceiling wooden bookshelves packed with tiny leather-bound grimoires, a glowing cyan potion cauldron, brass astrolabe, sleeping tabby cat on a patterned rug, warm desk lamp casting inviting amber light, Blender Cycles clean render.",
        "negative_prompt": "blurry, flat 2d, messy geometry, lowres, text, watermark, overexposed",
        "tags": ["等距微縮", "場景模型", "暖光"],
    },

    # ========== IMAGE: 奇幻科幻 ==========
    {
        "id": "img_scifi_cyberpunk",
        "kind": "image",
        "category": "奇幻科幻",
        "title": "賽博龐克高空飛行車雨夜大都會",
        "ratio": "16:9",
        "prompt": "Epic wide-angle sci-fi concept art of a towering vertical cyberpunk megacity during a midnight drizzle. Layered elevated highways with sleek flying vehicles leaving light trails, colossal holographic koi swimming between obsidian skyscrapers, glowing Traditional Chinese neon signage, volumetric fog and rain mist, Blade Runner 2049 cinematic scale and lighting.",
        "negative_prompt": "blurry, lowres, daytime, flat lighting, muddy details, distorted vehicles, watermark",
        "tags": ["賽博龐克", "概念藝術", "大場景"],
    },
    {
        "id": "img_scifi_forest",
        "kind": "image",
        "category": "奇幻科幻",
        "title": "阿凡達風格生物發光夜光森林",
        "ratio": "16:9",
        "prompt": "Enchanted bioluminescent ancient forest at midnight, colossal moss-covered roots glowing with translucent cyan and violet mushrooms, floating luminescent spores drifting like fireflies above a crystal stream, ethereal moonbeams filtering through giant ferns, cinematic fantasy matte painting, ultra-high detail and atmospheric depth.",
        "negative_prompt": "daylight, dull colors, blurry, lowres, noisy artifacts, text, watermark",
        "tags": ["發光森林", "奇幻", "夜色"],
    },
    {
        "id": "img_scifi_orbital",
        "kind": "image",
        "category": "奇幻科幻",
        "title": "近地軌道太空站全景觀景窗",
        "ratio": "16:9",
        "prompt": "Ultra-realistic sci-fi interior of an orbital space station observation lounge. A lone astronaut in a sleek white EVA suit stands silhouetted before a panoramic curved glass dome overlooking the glowing blue curvature of Earth and golden sunrise along the atmosphere, crisp metallic reflections, cinematic IMAX 70mm film look.",
        "negative_prompt": "cartoon, anime, distorted Earth, blurry, low quality, lens dirt, watermark, text",
        "tags": ["太空", "IMAX", "科幻"],
    },

    # ========== VIDEO: 史詩運鏡 (Wan2.2) ==========
    {
        "id": "vid_cam_pullback",
        "kind": "video",
        "category": "史詩運鏡",
        "title": "極地探險家拉遠史詩揭幕（Pull-Back Reveal）",
        "ratio": "16:9",
        "prompt": "Close-up of an arctic explorer's frost-covered face squinting against blowing snow. The camera smoothly pulls back to reveal a lone figure in an orange parka standing amid a vast whiteout blizzard, pulling further back to show endless cracking blue glaciers under a dramatic stormy sky. Cinematic lighting, 35mm film grain, epic documentary cinematography.",
        "negative_prompt": "flickering, morphing, shaky camera, melting face, static frozen frame, blurry, watermark, text",
        "tags": ["拉遠運鏡", "Wan2.2 推薦", "史詩感"],
    },
    {
        "id": "vid_cam_forest_track",
        "kind": "video",
        "category": "史詩運鏡",
        "title": "晨霧古老森林低角度跟拍",
        "ratio": "16:9",
        "prompt": "Dense ancient redwood forest bathed in golden morning mist with shafts of sunlight piercing the canopy. A smooth low-angle tracking camera glides swiftly behind a traveler in a dark green cloak running along a mossy trail, kicking up fine dewdrops and autumn leaves. Rich volumetric depth, fluid cinematic motion.",
        "negative_prompt": "flickering, frame jitter, warped trees, morphing body, shaky camera, low quality, watermark",
        "tags": ["低角度跟拍", "丁達爾光", "動態"],
    },
    {
        "id": "vid_cam_drone_valley",
        "kind": "video",
        "category": "史詩運鏡",
        "title": "高山晨霧木屋橫移航拍（Pan Reveal）",
        "ratio": "16:9",
        "prompt": "Serene alpine mountain valley at sunrise, soft mist drifting gently across pine-covered slopes as warm golden sunlight crests the ridge. The camera executes a slow, steady horizontal pan from left to right, unveiling a cozy wooden cabin beside a mirror-like turquoise lake. Peaceful majestic nature cinematography.",
        "negative_prompt": "flickering, sudden jump cut, warped mountains, shaky camera, blurry, compression artifacts, watermark",
        "tags": ["航拍橫移", "自然風景", "穩鏡"],
    },

    # ========== VIDEO: 電影劇情與人物 ==========
    {
        "id": "vid_char_detective",
        "kind": "video",
        "category": "電影劇情與人物",
        "title": "雨夜偵探緩慢推鏡特寫（Slow Push-In）",
        "ratio": "16:9",
        "prompt": "A detective in a charcoal trench coat stands on a rain-slicked cobblestone street at night, slowly turning up his collar against the falling rain. The camera executes a smooth slow push-in from medium shot to a tight close-up on his focused eyes. Cold cyan streetlamp glow and warm neon reflections shimmering in puddles, 35mm film grain.",
        "negative_prompt": "flickering, morphing face, extra fingers, shaky camera, melting coat, blurry, watermark",
        "tags": ["緩慢推鏡", "懸疑", "雨夜"],
    },
    {
        "id": "vid_char_smile_wind",
        "kind": "video",
        "category": "電影劇情與人物",
        "title": "海風日落回眸微笑（適合圖生影片 I2V）",
        "ratio": "9:16",
        "prompt": "A young woman on a sunlit coastal boardwalk gently turns her head toward the camera with a warm natural smile as ocean breeze softly blows strands of her hair across her cheek. Sparkling golden sunlight reflects off the waves behind her, subtle handheld cinema camera feel, smooth 24fps natural motion.",
        "negative_prompt": "morphing face, distorted eyes, flickering hair, unnatural jerky motion, blurry, watermark",
        "tags": ["圖生影片", "人像微動", "豎屏"],
    },
    {
        "id": "vid_char_barista",
        "kind": "video",
        "category": "電影劇情與人物",
        "title": "精品咖啡拉花微距慢動作",
        "ratio": "9:16",
        "prompt": "Extreme close-up slow-motion shot of silky steamed milk pouring smoothly from a stainless steel pitcher into rich golden espresso crema, forming a delicate rosetta latte art pattern inside a matte ceramic cup. Soft rising steam illuminated by warm morning café window light, steady tripod camera.",
        "negative_prompt": "flickering liquid, morphing cup, messy splash, shaky camera, lowres, watermark",
        "tags": ["慢動作", "療癒", "微距"],
    },
    {
        "id": "vid_char_hanfu_rain",
        "kind": "video",
        "category": "電影劇情與人物",
        "title": "國風漢服少女微雨執傘回眸",
        "ratio": "9:16",
        "prompt": "A graceful young woman in a flowing celadon silk Song Dynasty hanfu stands on an ancient stone bridge in gentle spring rain, slowly tilting her oiled-paper umbrella upward and turning toward the camera with a serene smile as translucent silk ribbons sway softly in the breeze. Misty willow trees and shimmering ripples on the canal behind her, smooth 24fps cinema slow push-in.",
        "negative_prompt": "flickering fabric, morphing face, deformed umbrella, shaky camera, modern objects, watermark",
        "tags": ["國風漢服", "微雨回眸", "圖生影片"],
    },
    {
        "id": "vid_char_jp_crossing",
        "kind": "video",
        "category": "電影劇情與人物",
        "title": "日系少女海濱鐵道平交道風吹長髮",
        "ratio": "16:9",
        "prompt": "A young Japanese girl in a cream cardigan stands beside a sunlit coastal railway crossing overlooking the sparkling ocean, gently brushing wind-blown hair behind her ear while a green retro commuter train glides smoothly across the background. Warm golden afternoon sunlight, authentic 35mm film aesthetic, steady medium shot.",
        "negative_prompt": "flickering train, morphing hair, distorted face, shaky camera, lowres, watermark",
        "tags": ["日系電影", "海濱鐵道", "清新"],
    },

    # ========== VIDEO: 自然與萌寵 ==========
    {
        "id": "vid_pet_rabbit",
        "kind": "video",
        "category": "自然與萌寵",
        "title": "可愛白兔喝水與耳朵輕輕抖動",
        "ratio": "1:1",
        "prompt": "A fluffy white bunny sitting beside a clear glass of water on a sunlit wooden porch, gently lapping water while its soft long ears twitch curiously and its nose wiggles. Warm afternoon sunlight, natural shallow depth of field, steady close-up camera, adorable lifelike fur texture.",
        "negative_prompt": "morphing ears, flickering fur, distorted glass, jerky motion, blurry, watermark",
        "tags": ["萌寵", "自然細節", "圖生影片"],
    },
    {
        "id": "vid_nature_sakura",
        "kind": "video",
        "category": "自然與萌寵",
        "title": "春日櫻花林蔭道花瓣紛飛慢鏡",
        "ratio": "16:9",
        "prompt": "A tranquil cherry blossom avenue in spring sunlight, thousands of soft pink sakura petals drifting slowly through the warm breeze across a sunlit stone pathway. The camera glides gently forward at eye level, soft golden bokeh and sparkling light beams through blooming branches.",
        "negative_prompt": "flickering petals, strobe effect, shaky camera, warped trees, low quality, watermark",
        "tags": ["櫻花", "前進運鏡", "唯美"],
    },

    # ========== VIDEO: 商業產品展示 ==========
    {
        "id": "vid_prod_watch_orbit",
        "kind": "video",
        "category": "商業產品展示",
        "title": "機械錶 360° 軌道環繞廣告（Orbital Arc）",
        "ratio": "1:1",
        "prompt": "A luxury mechanical wristwatch resting on dark slate, intricate golden gears visibly ticking beneath the sapphire crystal. A smooth, steady 180-degree orbital arc camera glides slowly around the timepiece, catching sharp specular highlights across brushed titanium edges. High-end studio commercial lighting.",
        "negative_prompt": "warping watch hands, flickering metal, shaky camera, blurry, distorted numbers, watermark",
        "tags": ["環繞運鏡", "產品廣告", "棚拍"],
    },
    {
        "id": "vid_prod_perfume_dolly",
        "kind": "video",
        "category": "商業產品展示",
        "title": "巴黎窗邊香水瓶優雅推鏡",
        "ratio": "16:9",
        "prompt": "By the tall window of a sunlit Parisian apartment, gilded afternoon light filters through sheer curtains onto a crystal perfume bottle surrounded by scattered rose petals on a marble table. The camera smoothly dollies forward while petals gently flutter in a soft breeze, shifting focus delicately onto the glass reflections.",
        "negative_prompt": "morphing bottle, flickering shadows, shaky camera, lowres, text overlay, watermark",
        "tags": ["推鏡", "香氛廣告", "光影"],
    },

    # ========== VIDEO: 有聲氛圍 (MiniMax-H3) ==========
    {
        "id": "vid_audio_cafe_rain",
        "kind": "video",
        "category": "有聲氛圍 (MiniMax-H3)",
        "title": "雨夜爵士咖啡廳窗景（含雨聲與輕音樂）",
        "ratio": "16:9",
        "prompt": "Inside a warm wooden café at night, raindrops streak slowly down the glass window overlooking blurred glowing city traffic while steam curls gently from a hot cappuccino on the table. Gentle acoustic rain tapping on glass, soft mellow jazz piano melody, and faint cozy café ambiance in the background. Steady intimate medium shot.",
        "negative_prompt": "flickering raindrops, morphing cup, shaky camera, static frozen frame, watermark, subtitles",
        "tags": ["有聲影片", "雨聲爵士", "MiniMax-H3"],
    },
    {
        "id": "vid_audio_nightmarket",
        "kind": "video",
        "category": "有聲氛圍 (MiniMax-H3)",
        "title": "台灣夜市鐵板料理熱鬧煙火氣（含現場音效）",
        "ratio": "16:9",
        "prompt": "Vibrant Taiwanese night market food stall at dusk, a chef deftly tossing sizzling diced steak and garlic on a hot cast-iron griddle as fragrant white smoke rises under warm glowing lanterns. Crisp sizzling audio from the grill, lively evening market chatter, and gentle ambient street sounds. Smooth cinematic tracking shot.",
        "negative_prompt": "flickering smoke, distorted hands, morphing food, shaky camera, blurry, watermark",
        "tags": ["有聲影片", "煙火氣", "MiniMax-H3"],
    },
    {
        "id": "vid_audio_ocean_dawn",
        "kind": "video",
        "category": "有聲氛圍 (MiniMax-H3)",
        "title": "清晨海浪拍岸與海鷗鳴叫（含環境海浪聲）",
        "ratio": "16:9",
        "prompt": "Golden dawn light breaking over a peaceful rocky coastline as turquoise ocean waves roll smoothly onto wet sand and gently recede into glistening foam, a few seagulls gliding across the pastel sky. Rhythmic soothing ocean surf sounds, soft coastal wind, and distant seagull calls. Slow steady wide-angle shot.",
        "negative_prompt": "flickering water, unnatural wave freeze, shaky camera, compression artifacts, watermark",
        "tags": ["有聲影片", "海浪聲", "療癒"],
    },
]


def _load_custom() -> List[Dict[str, Any]]:
    if not CUSTOM_PROMPTS_PATH.exists():
        return []
    try:
        return json.loads(CUSTOM_PROMPTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_custom(items: List[Dict[str, Any]]) -> None:
    CUSTOM_PROMPTS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_prompt_library(kind: Optional[str] = None) -> Dict[str, Any]:
    custom = _load_custom()
    all_prompts = [{**c, "is_custom": True} for c in custom] + [
        {**b, "is_custom": False} for b in BUILTIN_PROMPTS
    ]
    if kind in ("image", "video"):
        prompts = [p for p in all_prompts if p.get("kind") == kind]
        negatives = [n for n in NEGATIVE_PRESETS if n.get("kind") in ("all", kind)]
    else:
        prompts = all_prompts
        negatives = list(NEGATIVE_PRESETS)

    categories: List[str] = []
    for p in prompts:
        cat = p.get("category", "未分類")
        if cat not in categories:
            categories.append(cat)

    return {
        "prompts": prompts,
        "negative_presets": negatives,
        "categories": categories,
    }


def add_custom_prompt(body: Dict[str, Any]) -> Dict[str, Any]:
    items = _load_custom()
    entry = {
        "id": f"custom_{uuid.uuid4().hex[:10]}",
        "kind": body.get("kind", "image"),
        "category": str(body.get("category", "我的收藏")).strip() or "我的收藏",
        "title": str(body.get("title", "自訂提示詞")).strip() or "自訂提示詞",
        "ratio": str(body.get("ratio", "1:1")),
        "prompt": str(body.get("prompt", "")).strip(),
        "negative_prompt": str(body.get("negative_prompt", "")).strip(),
        "tags": body.get("tags") or ["自訂"],
        "created_at": time.time(),
    }
    if not entry["prompt"]:
        raise ValueError("提示詞內容不能為空")
    items.insert(0, entry)
    _save_custom(items)
    return {**entry, "is_custom": True}


def delete_custom_prompt(prompt_id: str) -> bool:
    items = _load_custom()
    kept = [p for p in items if p.get("id") != prompt_id]
    if len(kept) != len(items):
        _save_custom(kept)
        return True
    return False
