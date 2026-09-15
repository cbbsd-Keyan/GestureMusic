#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>
#include <SPI.h>
#include <math.h>

// ======================================================
// ST7735S
// ======================================================

#define TFT_CS    10
#define TFT_DC    13
#define TFT_RST   14
#define TFT_MOSI  11
#define TFT_SCLK  12

Adafruit_ST7735 tft(
  TFT_CS,
  TFT_DC,
  TFT_RST
);

U8G2_FOR_ADAFRUIT_GFX u8g2;


// ======================================================
// COLORS
// ======================================================

uint16_t BG;
uint16_t PANEL;
uint16_t PANEL2;

uint16_t WHITE;
uint16_t DIM;

uint16_t CYAN;
uint16_t CYAN_DARK;

uint16_t PURPLE;
uint16_t PURPLE_DARK;

uint16_t PINK;

uint16_t GREEN;
uint16_t RED;
uint16_t ORANGE;
uint16_t BLUE_SOFT;


// ======================================================
// PAGE
// ======================================================

enum Page {

  PAGE_MENU,
  PAGE_COMPOSE_MODE,
  PAGE_COUNTDOWN,
  PAGE_RECORD,
  PAGE_GENERATING,
  PAGE_RESULT,
  PAGE_PREVIEW,
  PAGE_MOONLIGHT,
  PAGE_CANON,
  PAGE_ERROR

};

Page currentPage =
  PAGE_MENU;


// ======================================================
// TIME
// ======================================================

unsigned long pageStart = 0;
unsigned long lastFrame = 0;

float phase = 0;


// ======================================================
// 中文
// ======================================================

void setChineseFont() {

  u8g2.setFontMode(1);

  u8g2.setFontDirection(0);

  u8g2.setFont(
    u8g2_font_wqy16_t_gb2312
  );
}


void cn(
  int x,
  int y,
  const char* text,
  uint16_t color
) {

  u8g2.setForegroundColor(
    color
  );

  u8g2.setCursor(
    x,
    y
  );

  u8g2.print(
    text
  );
}


// ======================================================
// COLORS
// ======================================================

void initColors() {

  BG =
    tft.color565(
      2, 4, 10
    );

  PANEL =
    tft.color565(
      16, 24, 40
    );

  PANEL2 =
    tft.color565(
      44, 52, 72
    );

  WHITE =
    tft.color565(
      238, 245, 255
    );

  DIM =
    tft.color565(
      76, 90, 115
    );

  CYAN =
    tft.color565(
      25, 225, 255
    );

  CYAN_DARK =
    tft.color565(
      0, 55, 80
    );

  PURPLE =
    tft.color565(
      170, 75, 255
    );

  PURPLE_DARK =
    tft.color565(
      64, 28, 110
    );

  PINK =
    tft.color565(
      255, 55, 175
    );

  GREEN =
    tft.color565(
      60, 255, 150
    );

  RED =
    tft.color565(
      255, 60, 75
    );

  ORANGE =
    tft.color565(
      255, 165, 45
    );

  BLUE_SOFT =
    tft.color565(
      105, 165, 255
    );
}


// ======================================================
// COMMON DECORATION
// ======================================================

void drawCorners() {

  // 左上
  tft.drawFastHLine(
    3, 3,
    12,
    CYAN_DARK
  );

  tft.drawFastVLine(
    3, 3,
    8,
    CYAN_DARK
  );


  // 右上
  tft.drawFastHLine(
    145, 3,
    12,
    PURPLE_DARK
  );

  tft.drawFastVLine(
    156, 3,
    8,
    PURPLE_DARK
  );


  // 左下
  tft.drawFastHLine(
    3, 123,
    12,
    PURPLE_DARK
  );

  tft.drawFastVLine(
    3, 116,
    8,
    PURPLE_DARK
  );


  // 右下
  tft.drawFastHLine(
    145, 123,
    12,
    CYAN_DARK
  );

  tft.drawFastVLine(
    156, 116,
    8,
    CYAN_DARK
  );
}


void clearPage() {

  tft.fillScreen(
    BG
  );

  drawCorners();
}


// ======================================================
// TOP BAR
// ======================================================

void topBar(
  const char* left,
  const char* right,
  uint16_t statusColor
) {

  tft.fillRoundRect(
    5,
    4,
    150,
    15,
    4,
    PANEL
  );


  tft.fillCircle(
    11,
    11,
    3,
    statusColor
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    WHITE
  );


  tft.setCursor(
    18,
    8
  );


  tft.print(
    left
  );


  int rightW =
    strlen(right) * 6;


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    151 - rightW,
    8
  );


  tft.print(
    right
  );
}


// ======================================================
// SCANLINE
// ======================================================

void drawScanLine() {

  int y =
    23 +
    ((millis() / 35) % 94);


  tft.drawFastHLine(
    6,
    y,
    148,
    CYAN_DARK
  );
}


// ======================================================
// 音符
// ======================================================

void drawNote(
  int x,
  int y,
  uint16_t c
) {

  tft.fillCircle(
    x,
    y,
    4,
    c
  );


  tft.drawFastVLine(
    x + 4,
    y - 16,
    17,
    c
  );


  tft.drawFastHLine(
    x + 4,
    y - 16,
    8,
    c
  );
}


// ======================================================
// 指挥棒
// ======================================================

void drawBaton(
  int x,
  int y,
  float a,
  uint16_t color
) {

  int len =
    35;


  int x2 =
    x +
    cos(a) * len;


  int y2 =
    y -
    sin(a) * len;


  // 拖尾
  tft.drawLine(
    x,
    y,
    x2 - 4,
    y2 + 3,
    PURPLE_DARK
  );


  tft.drawLine(
    x,
    y,
    x2 - 2,
    y2 + 1,
    CYAN_DARK
  );


  // 棒
  tft.drawLine(
    x,
    y,
    x2,
    y2,
    color
  );


  // 手柄
  tft.fillCircle(
    x,
    y,
    3,
    PINK
  );


  // 尖端
  tft.fillCircle(
    x2,
    y2,
    2,
    WHITE
  );
}


// ======================================================
// 霓虹框
// ======================================================

void neonCard(
  int x,
  int y,
  int w,
  int h,
  bool active
) {

  if(active) {

    tft.fillRoundRect(
      x - 2,
      y - 2,
      w + 4,
      h + 4,
      6,
      CYAN_DARK
    );
  }


  tft.fillRoundRect(
    x,
    y,
    w,
    h,
    5,
    active
      ? PANEL
      : BG
  );


  tft.drawRoundRect(
    x,
    y,
    w,
    h,
    5,
    active
      ? CYAN
      : PANEL2
  );


  if(active) {

    tft.drawFastVLine(
      x + 3,
      y + 6,
      h - 12,
      PINK
    );
  }
}


// ======================================================
// PAGE 1
// 主菜单
// ======================================================

void pageMenu() {

  clearPage();

  topBar(
    "GESTURE",
    "SELECT",
    GREEN
  );


  // ------------------------------
  // 作曲区
  // ------------------------------

  neonCard(
    10,
    27,
    91,
    38,
    true
  );


  // 音符
  drawNote(
    24,
    51,
    CYAN
  );


  drawNote(
    36,
    43,
    PURPLE
  );


  cn(
    55,
    52,
    "作曲",
    WHITE
  );


  // 小音符粒子
  tft.fillCircle(
    87,
    37,
    1,
    PINK
  );

  tft.fillCircle(
    92,
    47,
    1,
    CYAN
  );


  // ------------------------------
  // 指挥区
  // ------------------------------

  neonCard(
    10,
    73,
    140,
    31,
    false
  );


  cn(
    28,
    95,
    "指挥",
    DIM
  );


  float a =
    0.7 +
    0.25 *
    sin(
      phase
    );


  drawBaton(
    108,
    96,
    a,
    PURPLE
  );


  // 挥动轨迹
  tft.drawArc(
    108,
    96,
    33,
    27,
    190,
    245,
    CYAN_DARK
  );


  tft.setTextSize(1);

  tft.setTextColor(
    CYAN
  );


  tft.setCursor(
    53,
    116
  );


  tft.print(
    "< SELECT >"
  );
}


// ======================================================
// PAGE 2
// 作曲方式
// ======================================================

void drawModeIcon(
  int mode,
  int cx,
  int cy,
  bool active
) {

  uint16_t c =
    active
      ? CYAN
      : DIM;


  // 整体：圆环
  if(mode == 0) {

    tft.drawCircle(
      cx,
      cy,
      9,
      c
    );

    tft.drawCircle(
      cx,
      cy,
      5,
      active
        ? PURPLE
        : PANEL2
    );
  }


  // 起伏：波浪
  if(mode == 1) {

    int lastX =
      cx - 11;


    int lastY =
      cy;


    for(int i = 1; i <= 22; i++) {

      int x =
        cx - 11 + i;


      int y =
        cy +
        sin(
          i * 0.6
        )
        * 6;


      tft.drawLine(
        lastX,
        lastY,
        x,
        y,
        c
      );


      lastX =
        x;

      lastY =
        y;
    }
  }


  // 校准：准星
  if(mode == 2) {

    tft.drawCircle(
      cx,
      cy,
      7,
      c
    );


    tft.drawFastHLine(
      cx - 12,
      cy,
      24,
      c
    );


    tft.drawFastVLine(
      cx,
      cy - 12,
      24,
      c
    );


    tft.fillCircle(
      cx,
      cy,
      2,
      active
        ? PINK
        : DIM
    );
  }
}


void pageComposeMode() {

  clearPage();

  topBar(
    "COMPOSE",
    "MODE",
    CYAN
  );


  const char* labels[3] = {

    "整体",
    "起伏",
    "校准"
  };


  for(int i = 0; i < 3; i++) {

    int y =
      26 +
      i * 30;


    bool active =
      i == 1;


    neonCard(
      13,
      y,
      134,
      25,
      active
    );


    drawModeIcon(
      i,
      31,
      y + 12,
      active
    );


    cn(
      55,
      y + 18,
      labels[i],
      active
        ? WHITE
        : DIM
    );


    if(active) {

      tft.fillTriangle(
        136,
        y + 8,

        136,
        y + 17,

        142,
        y + 12,

        PINK
      );
    }
  }


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    PINK
  );


  tft.setCursor(
    36,
    118
  );


  tft.print(
    "DYNAMIC PROFILE"
  );
}


// ======================================================
// PAGE 3
// Countdown
// ======================================================

void pageCountdown() {

  clearPage();

  topBar(
    "COMPOSE",
    "READY",
    ORANGE
  );


  unsigned long e =
    millis() -
    pageStart;


  int number =
    3 -
    e / 750;


  number =
    constrain(
      number,
      1,
      3
    );


  float local =
    (e % 750)
    /
    750.0;


  int radius =
    36 -
    local * 15;


  // 外圈
  tft.drawCircle(
    80,
    65,
    radius + 7,
    CYAN_DARK
  );


  tft.drawCircle(
    80,
    65,
    radius + 2,
    PURPLE
  );


  tft.drawCircle(
    80,
    65,
    radius,
    CYAN
  );


  // 四个刻度
  tft.drawFastHLine(
    34,
    65,
    8,
    DIM
  );


  tft.drawFastHLine(
    118,
    65,
    8,
    DIM
  );


  tft.drawFastVLine(
    80,
    20,
    8,
    DIM
  );


  tft.drawFastVLine(
    80,
    102,
    8,
    DIM
  );


  // 大数字
  tft.setTextSize(
    5
  );


  tft.setTextColor(
    WHITE
  );


  tft.setCursor(
    66,
    44
  );


  tft.print(
    number
  );


  // 准备
  cn(
    63,
    117,
    "准备",
    CYAN
  );


  // 三点
  for(int i = 0; i < 3; i++) {

    tft.fillCircle(
      62 + i * 18,
      104,
      2,
      i <= 3 - number
        ? PINK
        : PANEL2
    );
  }
}


// ======================================================
// PAGE 4
// Recording
// ======================================================

void pageRecord() {

  clearPage();

  topBar(
    "COMPOSE",
    "RECORD",
    RED
  );


  // REC blink
  if(
    (
      millis() /
      250
    )
    %
    2
  ) {

    tft.fillCircle(
      145,
      11,
      3,
      RED
    );
  }


  // 网格背景

  for(int x = 12; x <= 148; x += 17) {

    tft.drawFastVLine(
      x,
      28,
      57,
      CYAN_DARK
    );
  }


  for(int y = 30; y <= 84; y += 13) {

    tft.drawFastHLine(
      8,
      y,
      144,
      CYAN_DARK
    );
  }


  // 动态波形

  int lastY =
    59;


  for(int x = 8; x < 152; x++) {

    float value =

      sin(
        x * 0.10 +
        phase * 2.5
      )

      +

      0.35 *
      sin(
        x * 0.31 +
        phase * 1.2
      );


    int y =
      59 +
      value *
      12;


    if(x > 8) {

      tft.drawLine(
        x - 1,
        lastY,
        x,
        y + 1,
        PURPLE
      );


      tft.drawLine(
        x - 1,
        lastY - 1,
        x,
        y,
        CYAN
      );
    }


    lastY =
      y;
  }


  // 指挥棒

  float angle =
    0.75 +
    0.50 *
    sin(
      phase * 1.8
    );


  drawBaton(
    76,
    74,
    angle,
    WHITE
  );


  // 录制时间

  int seconds =
    (
      millis() -
      pageStart
    )
    /
    180;


  seconds =
    constrain(
      seconds,
      0,
      15
    );


  float p =
    seconds /
    15.0;


  // progress

  tft.fillRoundRect(
    9,
    96,
    142,
    9,
    4,
    PANEL
  );


  int pw =
    138 *
    p;


  if(pw > 0) {

    tft.fillRoundRect(
      11,
      98,
      pw,
      5,
      2,
      PURPLE
    );


    tft.fillCircle(
      11 + pw,
      100,
      3,
      CYAN
    );
  }


  char timeText[12];


  sprintf(
    timeText,
    "%02d / 15s",
    seconds
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    WHITE
  );


  tft.setCursor(
    54,
    114
  );


  tft.print(
    timeText
  );
}


// ======================================================
// PAGE 5
// Generating
// ======================================================

void pageGenerating() {

  clearPage();

  topBar(
    "COMPOSE",
    "AI CORE",
    PURPLE
  );


  int cx =
    80;


  int cy =
    59;


  // 轨道
  tft.drawCircle(
    cx,
    cy,
    33,
    CYAN_DARK
  );


  tft.drawCircle(
    cx,
    cy,
    25,
    PURPLE_DARK
  );


  // 三颗卫星
  for(int i = 0; i < 3; i++) {

    float a =
      phase * 1.7 +
      i * 2.094;


    int x =
      cx +
      cos(a) * 33;


    int y =
      cy +
      sin(a) * 33;


    uint16_t c =
      i == 0
        ? CYAN
        :
        (
          i == 1
            ? PURPLE
            : PINK
        );


    tft.fillCircle(
      x,
      y,
      4,
      c
    );


    tft.drawCircle(
      x,
      y,
      6,
      c
    );
  }


  // 中央发光音符

  int pulse =
    1 +
    2 *
    (
      0.5 +
      0.5 *
      sin(
        phase * 2
      )
    );


  tft.fillCircle(
    75,
    64,
    5 + pulse,
    PINK
  );


  tft.fillCircle(
    75,
    64,
    4,
    WHITE
  );


  tft.drawFastVLine(
    80,
    42,
    22,
    WHITE
  );


  tft.drawFastHLine(
    80,
    42,
    10,
    WHITE
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    46,
    97
  );


  tft.print(
    "MUSIC ENGINE"
  );


  cn(
    51,
    117,
    "生成中",
    CYAN
  );


  // 三个 loading 点

  int active =
    (
      millis() /
      180
    )
    %
    3;


  for(int i = 0; i < 3; i++) {

    tft.fillCircle(
      104 + i * 8,
      113,
      2,
      i == active
        ? PINK
        : PANEL2
    );
  }
}


// ======================================================
// PAGE 6
// Result
// ======================================================

void pageResult() {

  clearPage();

  topBar(
    "COMPOSE",
    "DONE",
    GREEN
  );


  // 左边专辑封面

  tft.fillRoundRect(
    9,
    29,
    67,
    66,
    6,
    PANEL
  );


  tft.drawRoundRect(
    9,
    29,
    67,
    66,
    6,
    CYAN_DARK
  );


  // 封面顶部装饰

  tft.drawFastHLine(
    15,
    37,
    55,
    PURPLE
  );


  // 锯齿波封面

  int lastX =
    16;


  int lastY =
    65;


  for(int x = 17; x <= 69; x += 4) {

    int y =
      63 +
      sin(
        x * 0.8
      )
      * 18;


    tft.drawLine(
      lastX,
      lastY,
      x,
      y,
      CYAN
    );


    lastX =
      x;

    lastY =
      y;
  }


  // 右侧结果

  cn(
    90,
    45,
    "激烈",
    WHITE
  );


  tft.setTextSize(
    2
  );


  tft.setTextColor(
    PINK
  );


  tft.setCursor(
    87,
    60
  );


  tft.print(
    "125"
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    125,
    67
  );


  tft.print(
    "BPM"
  );


  // BPM徽章

  tft.drawRoundRect(
    85,
    54,
    65,
    22,
    5,
    PURPLE
  );


  // READY

  tft.setTextColor(
    GREEN
  );


  tft.setCursor(
    94,
    84
  );


  tft.print(
    "TRACK READY"
  );


  // 底部按钮

  tft.fillRoundRect(
    7,
    105,
    45,
    17,
    4,
    PANEL
  );


  tft.fillRoundRect(
    57,
    105,
    45,
    17,
    4,
    PANEL
  );


  tft.fillRoundRect(
    107,
    105,
    46,
    17,
    4,
    PANEL
  );


  tft.setTextColor(
    CYAN
  );


  tft.setCursor(
    17,
    110
  );


  tft.print(
    "> PLAY"
  );


  tft.setTextColor(
    GREEN
  );


  tft.setCursor(
    66,
    110
  );


  tft.print(
    "+ SAVE"
  );


  tft.setTextColor(
    ORANGE
  );


  tft.setCursor(
    111,
    110
  );


  tft.print(
    "RETRY"
  );
}


// ======================================================
// PAGE 7
// Preview
// ======================================================

void pagePreview() {

  clearPage();

  topBar(
    "COMPOSE",
    "PREVIEW",
    GREEN
  );


  // 大播放按钮

  tft.drawCircle(
    27,
    55,
    17,
    CYAN
  );


  tft.drawCircle(
    27,
    55,
    20,
    CYAN_DARK
  );


  tft.fillTriangle(
    23,
    46,
    23,
    64,
    36,
    55,
    WHITE
  );


  // 曲名

  cn(
    58,
    50,
    "激烈",
    WHITE
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    58,
    61
  );


  tft.print(
    "125 BPM"
  );


  // 播放轨道

  tft.drawFastHLine(
    12,
    82,
    136,
    PANEL2
  );


  int progress =
    (
      millis() -
      pageStart
    )
    /
    15;


  progress %=
    136;


  tft.drawFastHLine(
    12,
    82,
    progress,
    PURPLE
  );


  tft.fillCircle(
    12 + progress,
    82,
    3,
    CYAN
  );


  // 能量柱

  for(int i = 0; i < 14; i++) {

    float value =
      0.5 +
      0.5 *
      sin(
        phase * 2 +
        i * 0.55
      );


    int h =
      4 +
      value * 20;


    uint16_t c =
      i < 5
        ? CYAN
        :
        (
          i < 10
            ? PURPLE
            : PINK
        );


    tft.fillRect(
      7 + i * 11,
      117 - h,
      6,
      h,
      c
    );
  }
}


// ======================================================
// PAGE 8
// Moonlight
// ======================================================

void pageMoonlight() {

  clearPage();

  topBar(
    "CONDUCT",
    "MOONLIGHT",
    BLUE_SOFT
  );


  // 星星

  int starsX[7] = {

    18, 39, 56, 110, 129, 143, 101
  };


  int starsY[7] = {

    30, 46, 28, 34, 49, 26, 56
  };


  for(int i = 0; i < 7; i++) {

    int glow =
      (
        (
          millis() /
          250
        )
        +
        i
      )
      %
      2;


    tft.fillCircle(
      starsX[i],
      starsY[i],
      glow
        ? 2
        : 1,
      glow
        ? WHITE
        : BLUE_SOFT
    );
  }


  // 月牙
  tft.fillCircle(
    48,
    59,
    24,
    BLUE_SOFT
  );


  tft.fillCircle(
    58,
    52,
    22,
    BG
  );


  // 月光外晕

  int halo =
    29 +
    2 *
    sin(
      phase
    );


  tft.drawCircle(
    48,
    59,
    halo,
    CYAN_DARK
  );


  // 曲名

  cn(
    91,
    62,
    "月光",
    WHITE
  );


  // PLAY symbol

  tft.fillTriangle(
    103,
    70,
    103,
    86,
    116,
    78,
    PURPLE
  );


  // Energy

  float energy =
    0.5 +
    0.45 *
    sin(
      phase
    );


  tft.fillRoundRect(
    13,
    102,
    134,
    9,
    4,
    PANEL
  );


  int width =
    130 *
    energy;


  tft.fillRoundRect(
    15,
    104,
    width,
    5,
    2,
    BLUE_SOFT
  );


  tft.fillCircle(
    15 + width,
    106,
    4,
    WHITE
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    50,
    117
  );


  tft.print(
    "MOON ENERGY"
  );
}


// ======================================================
// PAGE 9
// CANON
// ======================================================

void drawCanonTrack(
  int y,
  char label,
  int type,
  bool active,
  uint16_t color
) {

  tft.setTextSize(
    2
  );


  tft.setTextColor(
    active
      ? WHITE
      : DIM
  );


  tft.setCursor(
    10,
    y - 5
  );


  tft.print(
    label
  );


  // rail

  tft.drawFastHLine(
    34,
    y,
    104,
    active
      ? color
      : PANEL2
  );


  if(type == 0) {

    // K：和弦块

    for(int i = 0; i < 8; i++) {

      int h =
        3 +
        (
          i % 3
        )
        * 3;


      tft.fillRect(
        39 + i * 11,
        y - h,
        6,
        h * 2,
        active
          ? color
          : PANEL2
      );
    }
  }


  if(type == 1) {

    // B：低频粗波

    for(int x = 38; x < 130; x++) {

      int yy =
        y +
        sin(
          x * 0.08 +
          phase
        )
        * 3;


      tft.drawPixel(
        x,
        yy,
        active
          ? color
          : PANEL2
      );


      tft.drawPixel(
        x,
        yy + 1,
        active
          ? color
          : PANEL2
      );
    }
  }


  if(type == 2) {

    // G：锯齿

    int px =
      38;


    int py =
      y;


    for(int x = 44; x < 132; x += 8) {

      int yy =
        (
          (
            x / 8
          )
          %
          2
        )
        ?
        y - 7
        :
        y + 7;


      tft.drawLine(
        px,
        py,
        x,
        yy,
        active
          ? color
          : PANEL2
      );


      px =
        x;

      py =
        yy;
    }
  }


  if(type == 3) {

    // D：鼓点

    for(int i = 0; i < 8; i++) {

      int r =
        (
          i % 2
        )
        ?
        2
        :
        4;


      tft.fillCircle(
        42 + i * 12,
        y,
        r,
        active
          ? color
          : PANEL2
      );
    }
  }


  // state dot

  tft.fillCircle(
    146,
    y,
    3,
    active
      ? color
      : PANEL2
  );
}


void pageCanon() {

  clearPage();

  topBar(
    "CONDUCT",
    "CANON",
    PURPLE
  );


  cn(
    64,
    37,
    "卡农",
    WHITE
  );


  drawCanonTrack(
    51,
    'K',
    0,
    true,
    CYAN
  );


  drawCanonTrack(
    70,
    'B',
    1,
    true,
    PURPLE
  );


  drawCanonTrack(
    89,
    'G',
    2,
    true,
    PINK
  );


  drawCanonTrack(
    108,
    'D',
    3,
    false,
    ORANGE
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    43,
    118
  );


  tft.print(
    "3 / 4 LAYERS"
  );
}


// ======================================================
// PAGE 10
// ERROR
// ======================================================

void pageError() {

  clearPage();

  topBar(
    "SYSTEM",
    "ERROR",
    RED
  );


  // glitch stripes

  int shift =
    (
      millis() /
      160
    )
    %
    3;


  if(shift == 0) {

    tft.fillRect(
      5,
      37,
      150,
      3,
      RED
    );
  }


  if(shift == 1) {

    tft.fillRect(
      18,
      72,
      120,
      2,
      PURPLE
    );
  }


  if(shift == 2) {

    tft.fillRect(
      3,
      91,
      153,
      3,
      CYAN_DARK
    );
  }


  // 警告六边形感

  tft.drawTriangle(
    80,
    30,
    49,
    83,
    111,
    83,
    RED
  );


  tft.drawTriangle(
    80,
    34,
    54,
    79,
    106,
    79,
    PINK
  );


  // !

  tft.fillRect(
    77,
    46,
    6,
    20,
    RED
  );


  tft.fillCircle(
    80,
    73,
    3,
    RED
  );


  cn(
    48 + shift,
    102,
    "播放失败",
    RED
  );


  tft.setTextSize(
    1
  );


  tft.setTextColor(
    DIM
  );


  tft.setCursor(
    44 - shift,
    115
  );


  tft.print(
    "SIGNAL // ERR04"
  );
}


// ======================================================
// DISPATCH
// ======================================================

void drawPage() {

  switch(
    currentPage
  ) {

    case PAGE_MENU:

      pageMenu();

      break;


    case PAGE_COMPOSE_MODE:

      pageComposeMode();

      break;


    case PAGE_COUNTDOWN:

      pageCountdown();

      break;


    case PAGE_RECORD:

      pageRecord();

      break;


    case PAGE_GENERATING:

      pageGenerating();

      break;


    case PAGE_RESULT:

      pageResult();

      break;


    case PAGE_PREVIEW:

      pagePreview();

      break;


    case PAGE_MOONLIGHT:

      pageMoonlight();

      break;


    case PAGE_CANON:

      pageCanon();

      break;


    case PAGE_ERROR:

      pageError();

      break;
  }
}


// ======================================================
// 哪些页面需要动画刷新
// ======================================================

bool isAnimatedPage() {

  return

    currentPage ==
      PAGE_MENU

    ||

    currentPage ==
      PAGE_COUNTDOWN

    ||

    currentPage ==
      PAGE_RECORD

    ||

    currentPage ==
      PAGE_GENERATING

    ||

    currentPage ==
      PAGE_PREVIEW

    ||

    currentPage ==
      PAGE_MOONLIGHT

    ||

    currentPage ==
      PAGE_CANON

    ||

    currentPage ==
      PAGE_ERROR;
}


// ======================================================
// 页面持续时间
// ======================================================

unsigned long pageDuration() {

  switch(
    currentPage
  ) {

    case PAGE_COUNTDOWN:

      return 2300;


    case PAGE_RECORD:

      return 3000;


    case PAGE_GENERATING:

      return 2800;


    case PAGE_PREVIEW:

      return 3000;


    case PAGE_MOONLIGHT:

      return 3000;


    case PAGE_CANON:

      return 3000;


    default:

      return 2600;
  }
}


// ======================================================
// 简单扫描切页
// ======================================================

void pageTransition() {

  for(int y = 0; y < 128; y += 8) {

    tft.fillRect(
      0,
      y,
      160,
      3,
      BG
    );


    tft.drawFastHLine(
      0,
      y + 3,
      160,
      CYAN_DARK
    );


    delay(
      4
    );
  }


  tft.fillScreen(
    BG
  );
}


// ======================================================
// SETUP
// ======================================================

void setup() {

  Serial.begin(
    115200
  );


  SPI.begin(
    TFT_SCLK,
    -1,
    TFT_MOSI,
    TFT_CS
  );


  tft.initR(
    INITR_BLACKTAB
  );


  tft.setRotation(
    1
  );


  u8g2.begin(
    tft
  );


  setChineseFont();

  initColors();


  currentPage =
    PAGE_MENU;


  pageStart =
    millis();


  drawPage();
}


// ======================================================
// LOOP
// ======================================================

void loop() {

  unsigned long now =
    millis();


  // ------------------------------------
  // 动画约12.5FPS
  // ------------------------------------

  if(
    now - lastFrame >=
    80
  ) {

    lastFrame =
      now;


    phase +=
      0.13;


    if(
      isAnimatedPage()
    ) {

      drawPage();
    }
  }


  // ------------------------------------
  // 自动切页
  // ------------------------------------

  if(
    now - pageStart >=
    pageDuration()
  ) {

    pageTransition();


    currentPage =
      (Page)(
        (
          (int)currentPage +
          1
        )
        %
        10
      );


    pageStart =
      millis();


    drawPage();
  }
}