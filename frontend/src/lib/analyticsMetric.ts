export const SUCCESS_RATE_COLOR_GREEN = "#52c41a";
export const SUCCESS_RATE_COLOR_ORANGE = "#fa8c16";
export const SUCCESS_RATE_COLOR_RED = "#ff4d4f";

export function getSuccessRateColor(rate: number): string {
  if (rate >= 95) return SUCCESS_RATE_COLOR_GREEN;
  if (rate >= 90) return SUCCESS_RATE_COLOR_ORANGE;
  return SUCCESS_RATE_COLOR_RED;
}
