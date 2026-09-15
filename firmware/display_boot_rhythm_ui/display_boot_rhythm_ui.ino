#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>
#include <SPI.h>
#include <math.h>

// ======================================================
// ST7735S
// 接线：
// SCL  -> GPIO12
// SDA  -> GPIO11
// CS   -> GPIO10
// DC   -> GPIO13
// RES  -> GPIO14
// ======================================================

#define TFT_CS    10
#define TFT_DC    13
#define TFT_RST   14
#define TFT_MOSI  11
#define TFT_SCLK  12

Adafruit_ST7735 tft(TFT_CS, TFT_DC, TFT_RST);
U8G2_FOR_ADAFRUIT_GFX u8g2;

// ======================================================
// 基础颜色
// ======================================================

uint16_t C_BG;
uint16_t C_PANEL;
uint16_t C_WHITE;
uint16_t C_BLACK;
uint16_t C_GRAY;
uint16_t C_CYAN;
uint16_t C_CYAN_DARK;
uint16_t C_PURPLE;
uint16_t C_PURPLE_DARK;
uint16_t C_PINK;
uint16_t C_GREEN;
uint16_t C_RED;
uint16_t C_ORANGE;

// ======================================================
// 咕嘎一家队角色颜色
// ======================================================

uint16_t GG_SKIN;
uint16_t GG_HAIR;
uint16_t GG_HAIR_LIGHT;
uint16_t GG_EYE;
uint16_t GG_EYE_DARK;
uint16_t GG_BODY;
uint16_t GG_BODY_SHADOW;
uint16_t GG_ORANGE;
uint16_t GG_BLUSH;

// ======================================================
// 主界面 DEMO 数据
// ======================================================

int bpm = 65;
float intensity = 0.55;
float motionValue = 0.50;

int beatNumber = 1;
float beatStrength = 1.0;
float phase = 0;

unsigned long lastBeat = 0;
unsigned long pulseStart = 0;
unsigned long lastFrame = 0;
unsigned long startTime = 0;

// ======================================================
// 波形区域
// ======================================================

#define WX 4
#define WY 89
#define WW 152
#define WH 26

int waveX = WX + 2;
int lastWaveY = WY + WH / 2;

// ======================================================
// 动画数学
// ======================================================

float smoothStep(float x) {
  x = constrain(x, 0.0, 1.0);
  return x * x * (3.0 - 2.0 * x);
}

float easeOutCubic(float x) {
  x = constrain(x, 0.0, 1.0);
  return 1.0 - pow(1.0 - x, 3);
}

float easeOutBack(float x) {
  const float c1 = 1.70158;
  const float c3 = c1 + 1.0;

  x = constrain(x, 0.0, 1.0);

  return 1.0
         + c3 * pow(x - 1.0, 3)
         + c1 * pow(x - 1.0, 2);
}

// ======================================================
// 中文字体
// ======================================================

void setChineseFont() {
  u8g2.setFontMode(1);
  u8g2.setFontDirection(0);
  u8g2.setFont(u8g2_font_wqy16_t_gb2312);
}

void drawChineseText(
  int x,
  int y,
  const char* text,
  uint16_t color
) {
  u8g2.setForegroundColor(color);
  u8g2.setCursor(x, y);
  u8g2.print(text);
}

// ======================================================
// 初始化颜色
// ======================================================

void initColors() {
  C_BG          = tft.color565(2, 4, 10);
  C_PANEL       = tft.color565(15, 22, 36);
  C_WHITE       = tft.color565(235, 245, 255);
  C_BLACK       = tft.color565(18, 18, 24);
  C_GRAY        = tft.color565(72, 85, 108);
  C_CYAN        = tft.color565(25, 225, 255);
  C_CYAN_DARK   = tft.color565(0, 55, 75);
  C_PURPLE      = tft.color565(165, 75, 255);
  C_PURPLE_DARK = tft.color565(65, 28, 105);
  C_PINK        = tft.color565(255, 55, 175);
  C_GREEN       = tft.color565(55, 255, 145);
  C_RED         = tft.color565(255, 70, 85);
  C_ORANGE      = tft.color565(255, 155, 35);

  GG_SKIN        = tft.color565(255, 221, 206);
  GG_HAIR        = tft.color565(44, 39, 45);
  GG_HAIR_LIGHT  = tft.color565(82, 73, 78);
  GG_EYE         = tft.color565(202, 108, 122);
  GG_EYE_DARK    = tft.color565(85, 38, 47);
  GG_BODY        = tft.color565(242, 222, 185);
  GG_BODY_SHADOW = tft.color565(211, 190, 156);
  GG_ORANGE      = tft.color565(194, 77, 27);
  GG_BLUSH       = tft.color565(250, 146, 158);
}

// ======================================================
// 开屏背景
// ======================================================

void drawBootBG() {
  tft.fillScreen(C_BG);

  tft.drawFastHLine(6, 9, 28, C_CYAN_DARK);
  tft.drawFastHLine(126, 9, 28, C_PURPLE_DARK);
  tft.drawFastHLine(7, 118, 20, C_PURPLE_DARK);
  tft.drawFastHLine(133, 118, 20, C_CYAN_DARK);

  tft.fillCircle(14, 18, 1, C_PINK);
  tft.fillCircle(22, 15, 1, C_CYAN);
  tft.fillCircle(28, 21, 1, C_PINK);
}

// ======================================================
// ① 队名动画：咕嘎一家队
// 总时长约 2 秒
// ======================================================

void teamIntroFast() {
  const char* chars[5] = {
    "咕",
    "嘎",
    "一",
    "家",
    "队"
  };

  int tx[5] = {40, 56, 72, 88, 104};
  int ty = 67;

  int sx[5] = {-25, 180, -25, 180, 80};
  int sy[5] = {18, 18, 110, 110, -25};

  drawBootBG();

  unsigned long introStart = millis();

  // 五个字飞入
  while (millis() - introStart < 950) {
    unsigned long elapsed = millis() - introStart;

    float t = (float)elapsed / 950.0;
    t = constrain(t, 0.0, 1.0);

    float ex = easeOutBack(t);
    float ey = smoothStep(t);

    tft.fillRect(0, 23, 160, 79, C_BG);
    tft.drawFastHLine(35, 82, 90, C_CYAN_DARK);

    for (int i = 0; i < 5; i++) {
      int x = sx[i] + (int)((tx[i] - sx[i]) * ex);
      int y = sy[i] + (int)((ty - sy[i]) * ey);

      drawChineseText(x + 3, y + 2, chars[i], C_PURPLE_DARK);
      drawChineseText(x - 1, y, chars[i], C_PINK);
      drawChineseText(x, y, chars[i], C_CYAN);
    }

    delay(28);
  }

  // 固定最终位置
  tft.fillRect(0, 23, 160, 79, C_BG);

  for (int i = 0; i < 5; i++) {
    drawChineseText(tx[i] + 2, ty + 2, chars[i], C_PURPLE_DARK);
    drawChineseText(tx[i], ty, chars[i], C_CYAN);
  }

  // 霓虹线展开
  unsigned long lineStart = millis();

  while (millis() - lineStart < 350) {
    float t = (float)(millis() - lineStart) / 350.0;
    t = constrain(t, 0.0, 1.0);

    int half = (int)(56 * smoothStep(t));

    tft.drawFastHLine(80 - half, 78, half * 2, C_CYAN);

    if (half > 10) {
      int p = half - 8;
      tft.drawFastHLine(80 - p, 81, p * 2, C_PURPLE);
    }

    if (half > 5) {
      tft.fillCircle(80 - half, 78, 1, C_WHITE);
      tft.fillCircle(80 + half, 78, 1, C_WHITE);
    }

    delay(22);
  }

  // TEAM
  tft.setTextSize(1);
  tft.setTextColor(C_GRAY);
  tft.setCursor(68, 38);
  tft.print("TEAM");

  // 粒子
  tft.fillCircle(18, 57, 1, C_PINK);
  tft.fillCircle(27, 48, 1, C_CYAN);
  tft.fillCircle(140, 49, 1, C_PINK);
  tft.fillCircle(147, 61, 1, C_CYAN);

  // 补足约 2 秒
  while (millis() - introStart < 2000) {
    unsigned long now = millis();

    if (((now / 130) % 2) == 0) {
      tft.fillCircle(24, 78, 1, C_WHITE);
      tft.fillCircle(136, 78, 1, C_WHITE);
    } else {
      tft.fillCircle(24, 78, 1, C_CYAN);
      tft.fillCircle(136, 78, 1, C_PURPLE);
    }

    delay(25);
  }

  tft.fillScreen(C_BG);
  delay(30);
}

// ======================================================
// 二次元眼睛
// ======================================================

void drawAnimeEye(
  int x,
  int y,
  bool blink
) {
  if (blink) {
    tft.drawLine(x - 6, y, x - 1, y + 2, GG_EYE_DARK);
    tft.drawLine(x - 1, y + 2, x + 5, y, GG_EYE_DARK);
    return;
  }

  tft.fillRoundRect(x - 6, y - 5, 12, 10, 5, C_WHITE);
  tft.fillCircle(x, y, 4, GG_EYE);
  tft.fillCircle(x, y - 1, 3, GG_EYE_DARK);
  tft.fillCircle(x, y, 1, C_BLACK);

  tft.fillCircle(x - 2, y - 2, 1, C_WHITE);
  tft.drawPixel(x + 2, y + 2, C_WHITE);

  tft.drawFastHLine(x - 6, y - 5, 11, GG_EYE_DARK);
  tft.drawLine(x + 5, y - 5, x + 8, y - 7, GG_EYE_DARK);
}

// ======================================================
// 咕嘎一家队企鹅角色
// ======================================================

void drawGuguGaga(
  int cx,
  int cy,
  int kick,
  bool blink,
  int lean
) {
  cx += lean;

  // 翅膀
  tft.fillTriangle(
    cx - 20, cy + 4,
    cx - 37, cy + 42,
    cx - 17, cy + 32,
    GG_HAIR
  );

  tft.fillTriangle(
    cx + 20, cy + 4,
    cx + 37, cy + 42,
    cx + 17, cy + 32,
    GG_HAIR
  );

  // 身体
  tft.fillRoundRect(
    cx - 21, cy - 1,
    42, 63,
    16,
    GG_BODY
  );

  tft.fillRoundRect(
    cx - 15, cy + 15,
    30, 42,
    13,
    GG_BODY_SHADOW
  );

  tft.fillRoundRect(
    cx - 13, cy + 10,
    26, 39,
    12,
    GG_BODY
  );

  // 后脑头发
  tft.fillCircle(cx, cy - 25, 27, GG_HAIR);
  tft.fillRoundRect(cx - 27, cy - 31, 11, 36, 5, GG_HAIR);
  tft.fillRoundRect(cx + 16, cy - 31, 11, 36, 5, GG_HAIR);

  // 脸
  tft.fillRoundRect(
    cx - 21, cy - 43,
    42, 40,
    16,
    GG_SKIN
  );

  tft.fillTriangle(
    cx - 15, cy - 8,
    cx + 15, cy - 8,
    cx, cy + 3,
    GG_SKIN
  );

  // 刘海
  tft.fillTriangle(
    cx - 21, cy - 42,
    cx - 7, cy - 44,
    cx - 16, cy - 19,
    GG_HAIR
  );

  tft.fillTriangle(
    cx - 12, cy - 45,
    cx + 1, cy - 45,
    cx - 5, cy - 19,
    GG_HAIR
  );

  tft.fillTriangle(
    cx - 3, cy - 45,
    cx + 11, cy - 42,
    cx + 3, cy - 19,
    GG_HAIR
  );

  tft.fillTriangle(
    cx + 6, cy - 43,
    cx + 22, cy - 39,
    cx + 10, cy - 18,
    GG_HAIR
  );

  // 两边碎发
  tft.fillTriangle(
    cx - 19, cy - 35,
    cx - 12, cy - 37,
    cx - 21, cy - 13,
    GG_HAIR
  );

  tft.fillTriangle(
    cx + 14, cy - 36,
    cx + 21, cy - 33,
    cx + 20, cy - 13,
    GG_HAIR
  );

  // 发丝高光
  tft.drawLine(
    cx - 15, cy - 39,
    cx - 12, cy - 29,
    GG_HAIR_LIGHT
  );

  tft.drawLine(
    cx + 13, cy - 39,
    cx + 9, cy - 29,
    GG_HAIR_LIGHT
  );

  // 眼睛
  drawAnimeEye(cx - 9, cy - 19, blink);
  drawAnimeEye(cx + 9, cy - 19, blink);

  // 腮红
  tft.fillCircle(cx - 16, cy - 10, 2, GG_BLUSH);
  tft.fillCircle(cx + 16, cy - 10, 2, GG_BLUSH);

  // 鼻子
  tft.drawPixel(cx, cy - 11, GG_BLUSH);

  // 嘴
  tft.drawFastHLine(cx - 3, cy - 4, 6, GG_EYE_DARK);
  tft.drawPixel(cx + 3, cy - 5, GG_EYE_DARK);

  // 右脚
  int feetY = cy + 54;

  tft.fillTriangle(
    cx + 5, feetY,
    cx + 26, feetY + 8,
    cx + 13, feetY + 15,
    GG_ORANGE
  );

  tft.fillTriangle(
    cx + 8, feetY + 3,
    cx + 18, feetY + 16,
    cx + 1, feetY + 13,
    GG_ORANGE
  );

  // 左腿踹屏
  int legX = cx - 7;
  int legY = cy + 49;

  int footX = legX - kick;
  int footY = legY - kick / 6;

  tft.fillTriangle(
    legX, legY,
    legX - 8, legY + 6,
    footX, footY,
    GG_ORANGE
  );

  int footW = 13 + kick / 8;
  int footH = 8 + kick / 12;

  tft.fillRoundRect(
    footX - footW,
    footY - footH / 2,
    footW + 7,
    footH,
    4,
    GG_ORANGE
  );

  // 三个脚趾
  tft.fillTriangle(
    footX - footW, footY,
    footX - footW - 6, footY - 5,
    footX - footW + 3, footY + 1,
    GG_ORANGE
  );

  tft.fillTriangle(
    footX - footW, footY,
    footX - footW - 7, footY,
    footX - footW + 3, footY + 4,
    GG_ORANGE
  );

  tft.fillTriangle(
    footX - footW, footY,
    footX - footW - 5, footY + 6,
    footX - footW + 4, footY + 3,
    GG_ORANGE
  );
}

// ======================================================
// 蛛网裂屏
// ======================================================

void drawScreenCrackReal(
  int x,
  int y
) {
  // 中央破口
  tft.fillCircle(x, y, 4, C_BLACK);
  tft.drawCircle(x, y, 6, C_WHITE);
  tft.drawCircle(x, y, 10, C_WHITE);
  tft.drawCircle(x, y, 13, C_CYAN_DARK);

  // 主裂纹
  tft.drawLine(x, y, x - 44, y - 24, C_WHITE);
  tft.drawLine(x, y, x - 41, y + 20, C_WHITE);
  tft.drawLine(x, y, x - 11, y - 44, C_WHITE);
  tft.drawLine(x, y, x + 24, y - 34, C_WHITE);
  tft.drawLine(x, y, x + 42, y + 20, C_WHITE);
  tft.drawLine(x, y, x + 8, y + 43, C_WHITE);
  tft.drawLine(x, y, x - 27, y + 36, C_WHITE);
  tft.drawLine(x, y, x + 37, y - 7, C_WHITE);

  // 分叉
  tft.drawLine(x - 15, y - 8, x - 29, y - 4, C_CYAN);
  tft.drawLine(x - 25, y - 14, x - 31, y - 24, C_CYAN);
  tft.drawLine(x - 17, y + 10, x - 31, y + 5, C_CYAN);
  tft.drawLine(x - 7, y - 26, x - 1, y - 36, C_CYAN);
  tft.drawLine(x + 13, y - 18, x + 27, y - 12, C_CYAN);
  tft.drawLine(x + 20, y + 10, x + 33, y + 5, C_CYAN);
  tft.drawLine(x + 3, y + 23, x + 9, y + 35, C_CYAN);
  tft.drawLine(x - 14, y + 19, x - 21, y + 31, C_CYAN);

  // 细裂纹
  tft.drawLine(x - 32, y - 18, x - 40, y - 13, C_GRAY);
  tft.drawLine(x + 29, y + 14, x + 39, y + 11, C_GRAY);
  tft.drawLine(x + 14, y - 27, x + 15, y - 39, C_GRAY);
  tft.drawLine(x - 22, y + 27, x - 32, y + 30, C_GRAY);

  // 玻璃碎片
  tft.fillTriangle(
    x - 25, y - 18,
    x - 18, y - 26,
    x - 14, y - 16,
    C_WHITE
  );

  tft.fillTriangle(
    x + 18, y - 21,
    x + 29, y - 16,
    x + 18, y - 11,
    C_CYAN
  );

  tft.fillTriangle(
    x + 20, y + 15,
    x + 30, y + 20,
    x + 17, y + 23,
    C_WHITE
  );

  tft.fillTriangle(
    x - 21, y + 18,
    x - 13, y + 24,
    x - 23, y + 28,
    C_CYAN
  );
}

// ======================================================
// 企鹅动画单帧
// ======================================================

void drawPenguinScene(
  int cx,
  int cy,
  int kick,
  bool blink,
  int lean,
  bool crack
) {
  tft.fillScreen(C_BG);

  drawGuguGaga(
    cx,
    cy,
    kick,
    blink,
    lean
  );

  if (crack) {
    int footW = 13 + kick / 8;

    int impactX =
      cx
      - 7
      - kick
      - footW;

    int impactY =
      cy
      + 49
      - kick / 6;

    drawScreenCrackReal(
      impactX,
      impactY
    );
  }
}

// ======================================================
// ② 企鹅冲入 / 踹屏 / 裂屏 / 眨眼
// ======================================================

void guguEntranceAnimation() {
  // 冲入
  for (int i = 0; i <= 6; i++) {
    float t = (float)i / 6.0;
    float e = easeOutCubic(t);

    int x =
      205
      -
      (int)(
        114 * e
      );

    drawPenguinScene(
      x,
      62,
      0,
      false,
      0,
      false
    );

    delay(20);
  }

  // 停住
  drawPenguinScene(
    91,
    62,
    0,
    false,
    0,
    false
  );

  delay(45);

  // 蓄力
  for (int i = 0; i < 3; i++) {
    drawPenguinScene(
      91 + i * 2,
      62,
      3 + i * 3,
      false,
      2 + i * 2,
      false
    );

    delay(30);
  }

  // 猛踹
  for (int i = 0; i <= 4; i++) {
    float t = (float)i / 4.0;
    float e = easeOutCubic(t);

    int kick =
      8
      +
      (int)(
        22 * e
      );

    drawPenguinScene(
      94,
      62,
      kick,
      false,
      4,
      false
    );

    delay(23);
  }

  // 双白闪
  tft.fillScreen(C_WHITE);
  delay(25);

  tft.fillScreen(C_BG);
  delay(12);

  tft.fillScreen(C_WHITE);
  delay(12);

  // 震动 + 裂屏
  const int shakeX[8] = {
    -5, 5, -4, 4, -3, 2, -1, 0
  };

  const int shakeY[8] = {
    2, -2, 2, -2, 1, -1, 1, 0
  };

  for (int i = 0; i < 8; i++) {
    drawPenguinScene(
      94 + shakeX[i],
      62 + shakeY[i],
      30,
      false,
      4,
      true
    );

    delay(27);
  }

  // 收腿
  for (int kick = 27; kick >= 9; kick -= 5) {
    drawPenguinScene(
      83,
      62,
      kick,
      false,
      0,
      true
    );

    delay(28);
  }

  // 站稳
  drawPenguinScene(
    80,
    62,
    8,
    false,
    0,
    true
  );

  delay(120);

  // 眨眼
  drawPenguinScene(
    80,
    62,
    8,
    true,
    0,
    true
  );

  delay(75);

  drawPenguinScene(
    80,
    62,
    8,
    false,
    0,
    true
  );

  delay(150);
}

// ======================================================
// ③ GESTURE MUSIC
// 最后白球扩大吞屏
// ======================================================

void projectTitleAnimation() {
  tft.fillScreen(C_BG);

  // GESTURE / MUSIC 两侧滑入
  for (int i = 0; i <= 14; i++) {
    float t = (float)i / 14.0;
    float e = easeOutCubic(t);

    int gx =
      -80 +
      (int)(
        108 * e
      );

    int mx =
      170 -
      (int)(
        120 * e
      );

    tft.fillRect(
      0,
      24,
      160,
      75,
      C_BG
    );

    tft.drawFastHLine(
      7,
      64,
      146,
      C_PANEL
    );

    // GESTURE 阴影
    tft.setTextSize(2);
    tft.setTextColor(C_CYAN_DARK);
    tft.setCursor(gx + 2, 39);
    tft.print("GESTURE");

    // GESTURE 主体
    tft.setTextColor(C_CYAN);
    tft.setCursor(gx, 37);
    tft.print("GESTURE");

    // MUSIC 阴影
    tft.setTextColor(C_PURPLE_DARK);
    tft.setCursor(mx + 2, 69);
    tft.print("MUSIC");

    // MUSIC 主体
    tft.setTextColor(C_PURPLE);
    tft.setCursor(mx, 67);
    tft.print("MUSIC");

    delay(18);
  }

  // 标题停留
  delay(430);

  int cx = 80;
  int cy = 64;

  // 中央能量核心
  for (int r = 3; r <= 17; r += 3) {
    tft.drawCircle(cx, cy, r, C_CYAN);

    if (r > 7) {
      tft.drawCircle(
        cx,
        cy,
        r - 4,
        C_PURPLE
      );
    }

    tft.fillCircle(
      cx,
      cy,
      2,
      C_WHITE
    );

    delay(25);
  }

  // 白色核心扩大吞屏
  for (int r = 4; r <= 105; r += 5) {
    tft.fillCircle(
      cx,
      cy,
      r + 3,
      C_CYAN
    );

    if (r > 10) {
      tft.fillCircle(
        cx,
        cy,
        r + 1,
        C_PURPLE
      );
    }

    tft.fillCircle(
      cx,
      cy,
      r,
      C_WHITE
    );

    delay(12);
  }

  tft.fillScreen(C_WHITE);
  delay(100);
}

// ======================================================
// ④ SYSTEM ONLINE
// ======================================================

void systemOnlineAnimation() {
  tft.fillScreen(C_BG);

  // 核心启动
  for (int r = 2; r <= 13; r += 2) {
    tft.drawCircle(
      80,
      42,
      r,
      C_CYAN
    );

    if (r > 5) {
      tft.drawCircle(
        80,
        42,
        r - 5,
        C_PURPLE
      );
    }

    tft.fillCircle(
      80,
      42,
      2,
      C_WHITE
    );

    delay(22);
  }

  // SYSTEM ONLINE
  tft.setTextSize(1);
  tft.setTextColor(C_GREEN);
  tft.setCursor(42, 65);
  tft.print("SYSTEM ONLINE");

  const char* labels[3] = {
    "DISPLAY",
    "SIGNAL",
    "MOTION"
  };

  for (int i = 0; i < 3; i++) {
    int y =
      82 +
      i * 11;

    tft.setTextColor(C_GRAY);
    tft.setCursor(42, y);
    tft.print(labels[i]);

    delay(85);

    tft.setTextColor(C_GREEN);
    tft.setCursor(105, y);
    tft.print("OK");
  }

  // 停留
  delay(610);
}

// ======================================================
// ⑤ 百叶窗转场
// ======================================================

void transitionToMain() {
  const int bladeH = 8;

  // 多层百叶从左右向中央闭合
  for (int step = 0; step <= 80; step += 5) {
    for (int y = 0; y < 128; y += bladeH) {
      if ((y / bladeH) % 2 == 0) {
        tft.fillRect(
          0,
          y,
          step,
          bladeH - 1,
          C_BG
        );

        tft.fillRect(
          160 - step,
          y,
          step,
          bladeH - 1,
          C_BG
        );

      } else {
        int w =
          max(
            0,
            step - 8
          );

        tft.fillRect(
          0,
          y,
          w,
          bladeH - 1,
          C_BG
        );

        tft.fillRect(
          160 - w,
          y,
          w,
          bladeH - 1,
          C_BG
        );
      }

      tft.drawFastHLine(
        0,
        y + bladeH - 1,
        160,
        C_CYAN_DARK
      );
    }

    delay(18);
  }

  // 完全闭合
  tft.fillScreen(C_BG);

  // 中央最后一道光
  tft.drawFastHLine(
    18,
    64,
    124,
    C_CYAN
  );

  delay(80);

  tft.fillScreen(C_BG);
  delay(80);
}

// ======================================================
// 完整开机流程
// ======================================================

void bootAnimation() {
  teamIntroFast();
  guguEntranceAnimation();
  projectTitleAnimation();
  systemOnlineAnimation();
  transitionToMain();
}

// ======================================================
// 主界面底图
// ======================================================

void drawBaseUI() {
  tft.fillScreen(C_BG);

  // 顶栏
  tft.fillRoundRect(
    3,
    3,
    154,
    16,
    4,
    C_PANEL
  );

  tft.fillCircle(
    10,
    11,
    3,
    C_GREEN
  );

  tft.setTextSize(1);

  tft.setTextColor(C_CYAN);
  tft.setCursor(17, 8);
  tft.print("GESTURE");

  tft.setTextColor(C_PURPLE);
  tft.print(" MUSIC");

  tft.setTextColor(C_GREEN);
  tft.setCursor(113, 8);
  tft.print("LIVE");

  // 标签
  tft.setTextColor(C_GRAY);

  tft.setCursor(6, 24);
  tft.print("TEMPO");

  tft.setCursor(6, 66);
  tft.print("ENERGY");

  tft.setCursor(5, 82);
  tft.print("MOTION");

  // ENERGY 背景
  tft.fillRoundRect(
    5,
    76,
    70,
    5,
    2,
    C_PANEL
  );

  // 四拍
  for (int i = 0; i < 4; i++) {
    tft.drawCircle(
      96 + i * 11,
      76,
      2,
      C_GRAY
    );
  }

  // 波形框
  tft.drawRoundRect(
    WX,
    WY,
    WW,
    WH,
    3,
    C_PANEL
  );

  tft.drawFastHLine(
    WX + 2,
    WY + WH / 2,
    WW - 4,
    C_CYAN_DARK
  );

  // 底线
  tft.drawFastHLine(
    4,
    120,
    152,
    C_PANEL
  );
}

// ======================================================
// BPM
// ======================================================

void drawBPM() {
  static int oldBpm = -1000;

  if (oldBpm == bpm) {
    return;
  }

  oldBpm = bpm;

  tft.fillRect(
    5,
    31,
    73,
    31,
    C_BG
  );

  tft.setTextSize(3);

  // 阴影
  tft.setTextColor(C_CYAN_DARK);
  tft.setCursor(8, 34);
  tft.print(bpm);

  // 主数字
  tft.setTextColor(C_CYAN);
  tft.setCursor(6, 32);
  tft.print(bpm);

  tft.setTextSize(1);
  tft.setTextColor(C_WHITE);
  tft.setCursor(57, 51);
  tft.print("BPM");
}

// ======================================================
// ENERGY
// ======================================================

void drawIntensity() {
  int percent =
    constrain(
      (int)(
        intensity *
        100
      ),
      0,
      100
    );

  tft.fillRect(
    39,
    64,
    38,
    11,
    C_BG
  );

  tft.setTextSize(1);
  tft.setTextColor(C_PINK);
  tft.setCursor(41, 66);

  if (percent < 100) {
    tft.print(" ");
  }

  tft.print(percent);
  tft.print("%");

  // 清空强度条
  tft.fillRoundRect(
    5,
    76,
    70,
    5,
    2,
    C_PANEL
  );

  int w =
    (int)(
      68 *
      intensity
    );

  // 青
  int a =
    min(
      w,
      23
    );

  if (a > 0) {
    tft.fillRect(
      6,
      77,
      a,
      3,
      C_CYAN
    );
  }

  // 紫
  int b =
    constrain(
      w - 23,
      0,
      23
    );

  if (b > 0) {
    tft.fillRect(
      29,
      77,
      b,
      3,
      C_PURPLE
    );
  }

  // 粉
  int c =
    constrain(
      w - 46,
      0,
      22
    );

  if (c > 0) {
    tft.fillRect(
      52,
      77,
      c,
      3,
      C_PINK
    );
  }
}

// ======================================================
// 四拍指示
// ======================================================

void drawBeatDots() {
  for (int i = 0; i < 4; i++) {
    int x =
      96 +
      i * 11;

    tft.fillCircle(
      x,
      76,
      4,
      C_BG
    );

    if (i == beatNumber - 1) {
      uint16_t col =
        beatNumber == 1
        ?
        C_CYAN
        :
        C_PINK;

      tft.fillCircle(
        x,
        76,
        3,
        col
      );

      tft.drawCircle(
        x,
        76,
        4,
        C_PURPLE
      );

    } else {
      tft.drawCircle(
        x,
        76,
        2,
        C_GRAY
      );
    }
  }
}

// ======================================================
// 节拍呼吸包络
// ======================================================

float getBeatEnvelope() {
  unsigned long elapsed =
    millis()
    -
    pulseStart;

  if (elapsed >= 800) {
    return 0.0;
  }

  // Attack
  if (elapsed < 130) {
    float x =
      (float)elapsed /
      130.0;

    return
      smoothStep(x)
      *
      beatStrength;
  }

  // Release
  float x =
    (float)(
      elapsed - 130
    )
    /
    670.0;

  return
    (
      1.0 -
      smoothStep(x)
    )
    *
    beatStrength;
}

// ======================================================
// 节奏球
// ======================================================

void drawBeatCore() {
  tft.fillRect(
    79,
    21,
    80,
    43,
    C_BG
  );

  float e =
    getBeatEnvelope();

  int cx = 123;
  int cy = 43;

  int radius =
    6
    +
    (int)(
      10 * e
    );

  // 外环
  tft.drawCircle(
    cx,
    cy,
    radius + 9,
    C_CYAN_DARK
  );

  if (e > 0.15) {
    tft.drawCircle(
      cx,
      cy,
      radius + 6,
      C_PURPLE_DARK
    );
  }

  if (e > 0.40) {
    tft.drawCircle(
      cx,
      cy,
      radius + 3,
      C_PINK
    );
  }

  // 核心
  tft.fillCircle(
    cx,
    cy,
    radius,
    C_PURPLE
  );

  tft.fillCircle(
    cx,
    cy,
    max(
      2,
      radius - 3
    ),
    C_PINK
  );

  tft.fillCircle(
    cx,
    cy,
    max(
      2,
      radius - 7
    ),
    C_WHITE
  );

  // 第一拍更强
  if (
    beatNumber == 1
    &&
    e > 0.50
  ) {
    tft.drawCircle(
      cx,
      cy,
      radius + 13,
      C_CYAN
    );
  }

  // 四向粒子
  if (e > 0.65) {
    int p =
      4
      +
      (int)(
        5 * e
      );

    tft.drawFastHLine(
      cx - radius - p - 2,
      cy,
      p,
      C_CYAN
    );

    tft.drawFastHLine(
      cx + radius + 3,
      cy,
      p,
      C_CYAN
    );

    tft.drawFastVLine(
      cx,
      cy - radius - p - 2,
      p,
      C_PURPLE
    );

    tft.drawFastVLine(
      cx,
      cy + radius + 3,
      p,
      C_PURPLE
    );
  }

  // 两侧小频谱
  for (int i = 0; i < 4; i++) {
    float s =
      sin(
        phase * 1.7
        +
        i * 0.9
      );

    int h =
      3
      +
      (int)(
        fabs(s)
        *
        10
        *
        intensity
      );

    int lx =
      84 +
      i * 4;

    int rx =
      155 -
      i * 4;

    tft.drawFastVLine(
      lx,
      cy - h / 2,
      h,
      C_CYAN
    );

    tft.drawFastVLine(
      rx,
      cy - h / 2,
      h,
      C_PURPLE
    );
  }
}

// ======================================================
// MOTION 波形
// ======================================================

void drawWave(
  float value
) {
  value =
    constrain(
      value,
      0.0,
      1.0
    );

  int top =
    WY + 2;

  int bottom =
    WY + WH - 3;

  int y =
    bottom
    -
    (int)(
      value
      *
      (
        bottom - top
      )
    );

  // 清当前列
  tft.drawFastVLine(
    waveX,
    top,
    WH - 4,
    C_BG
  );

  // 恢复中心线
  tft.drawPixel(
    waveX,
    WY + WH / 2,
    C_CYAN_DARK
  );

  // 紫色残影
  tft.drawLine(
    waveX - 1,
    lastWaveY + 1,
    waveX,
    y + 1,
    C_PURPLE
  );

  // 主波形
  tft.drawLine(
    waveX - 1,
    lastWaveY,
    waveX,
    y,
    C_CYAN
  );

  if (value > 0.78) {
    tft.fillCircle(
      waveX,
      y,
      1,
      C_WHITE
    );
  }

  lastWaveY = y;
  waveX++;

  if (waveX >= WX + WW - 2) {
    waveX = WX + 2;
    lastWaveY = WY + WH / 2;
  }
}

// ======================================================
// 播放进度
// ======================================================

void drawProgress() {
  unsigned long play =
    millis()
    -
    startTime;

  const unsigned long total =
    90000;

  play %= total;

  float progress =
    (float)play /
    total;

  int sec =
    play /
    1000;

  char buf[6];

  sprintf(
    buf,
    "%02d:%02d",
    sec / 60,
    sec % 60
  );

  // 当前时间
  tft.fillRect(
    3,
    117,
    31,
    11,
    C_BG
  );

  tft.setTextSize(1);
  tft.setTextColor(C_GRAY);
  tft.setCursor(4, 120);
  tft.print(buf);

  // 总时间
  tft.fillRect(
    128,
    117,
    32,
    11,
    C_BG
  );

  tft.setCursor(130, 120);
  tft.print("01:30");

  // 进度条
  tft.drawFastHLine(
    36,
    124,
    89,
    C_PANEL
  );

  int w =
    (int)(
      89 *
      progress
    );

  if (w > 0) {
    tft.drawFastHLine(
      36,
      124,
      w,
      C_PURPLE
    );

    tft.fillCircle(
      36 + w,
      124,
      2,
      C_CYAN
    );
  }
}

// ======================================================
// DEMO 数据
// 后续可替换为电脑端 UDP 数据
// ======================================================

void updateDemo() {
  phase += 0.07;

  // Motion
  motionValue =
    0.47
    +
    0.24 *
    sin(
      phase
    )
    +
    0.13 *
    sin(
      phase * 2.4
    )
    +
    0.05 *
    sin(
      phase * 5.0
    );

  motionValue =
    constrain(
      motionValue,
      0.04,
      0.96
    );

  // Energy
  intensity =
    0.52
    +
    0.37 *
    sin(
      phase * 0.12
    );

  intensity =
    constrain(
      intensity,
      0.10,
      0.92
    );

  // BPM 约 55~75
  bpm =
    65
    +
    (int)(
      10 *
      sin(
        phase * 0.035
      )
    );
}

// ======================================================
// SETUP
// ======================================================

void setup() {
  Serial.begin(115200);

  // ESP32-S3 自定义硬件 SPI
  SPI.begin(
    TFT_SCLK,
    -1,
    TFT_MOSI,
    TFT_CS
  );

  // 已实测可用
  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);

  // 中文
  u8g2.begin(tft);
  setChineseFont();

  // 颜色
  initColors();

  // 开机动画
  bootAnimation();

  // 主界面
  drawBaseUI();

  startTime = millis();
  lastBeat = millis();
  pulseStart = millis();

  drawBPM();
  drawIntensity();
  drawBeatDots();
}

// ======================================================
// LOOP
// ======================================================

void loop() {
  unsigned long now = millis();

  // 约 20 FPS
  if (now - lastFrame >= 50) {
    lastFrame = now;

    updateDemo();

    // BPM -> beat
    unsigned long interval =
      60000UL /
      bpm;

    if (now - lastBeat >= interval) {
      lastBeat = now;
      pulseStart = now;

      beatNumber++;

      if (beatNumber > 4) {
        beatNumber = 1;
      }

      // 第一拍更重
      beatStrength =
        (
          beatNumber == 1
        )
        ?
        1.0
        :
        0.68;

      drawBeatDots();
    }

    drawBPM();
    drawIntensity();
    drawBeatCore();
    drawWave(motionValue);

    // 进度条约 5 FPS
    static int counter = 0;

    counter++;

    if (counter >= 4) {
      counter = 0;
      drawProgress();
    }
  }
}
