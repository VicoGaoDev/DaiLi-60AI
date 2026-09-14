export interface PromptInterceptionTipSection {
  title: string;
  items: string[];
}

export const PROMPT_INTERCEPTION_TIP_TITLE = "拦截内容提示";

export const PROMPT_INTERCEPTION_TIP_SECTIONS: PromptInterceptionTipSection[] = [
  {
    title: "易被拦截的提示词内容",
    items: [
      "色情、裸露、性暗示或低俗相关描述",
      "暴力、血腥、恐怖、武器、自残相关描述",
      "政治敏感、极端主义、邪教迷信等内容",
      "赌博、毒品、诈骗等违法违规内容",
      "侮辱、歧视、骚扰特定群体（尤其涉及未成年人）",
      "未经授权的真人姓名、肖像、品牌商标、版权角色（如迪士尼、漫威等）",
      "明确要求模仿知名公众人物或特定人物的写实生成",
    ],
  },
  {
    title: "易被拦截的参考图内容",
    items: [
      "含色情、裸露、性暗示或低俗画面的图片",
      "含暴力、血腥、恐怖元素的图片",
      "真人肖像、名人照片（未经授权）",
      "受版权保护的动漫、游戏、影视角色截图或素材",
      "含武器、毒品、赌博等违禁元素",
      "政治敏感标识、符号或人物相关图像",
    ],
  },
] as const;

export const PROMPT_INTERCEPTION_TIP_FOOTNOTE =
  "不同模型的内容审查尺度不同，若被拦截可尝试修改提示词或参考图，或更换模型后重试。";
