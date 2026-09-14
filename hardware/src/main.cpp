#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

// ========================
// 基本参数
// ========================
#define LED_PIN   18
#define LED_COUNT 16

Adafruit_NeoPixel strip(
    LED_COUNT,
    LED_PIN,
    NEO_GRB + NEO_KHZ800
);

// 默认 BPM
int bpm = 90;

// ========================
// 模式定义
// ========================
enum LedMode
{
    MODE_IDLE,
    MODE_GESTURE,
    MODE_WAITING,
    MODE_GENTLE,
    MODE_MODERATE,
    MODE_VIGOROUS,
    MODE_ERROR
};

LedMode currentMode = MODE_IDLE;

unsigned long modeStartTime = 0;

// ========================
// 一些颜色
// ========================
uint32_t BLACK   = strip.Color(0, 0, 0);
uint32_t RED     = strip.Color(255, 0, 0);
uint32_t GREEN   = strip.Color(0, 255, 0);
uint32_t BLUE    = strip.Color(0, 0, 255);
uint32_t CYAN    = strip.Color(0, 150, 128);
uint32_t PURPLE  = strip.Color(150, 0, 255);
uint32_t MAGENTA = strip.Color(255, 0, 180);
uint32_t ORANGE  = strip.Color(255, 80, 0);
uint32_t YELLOW  = strip.Color(150, 90, 0);


// ======================================================
// 工具函数
// ======================================================

// 切换模式
void setMode(LedMode newMode)
{
    currentMode = newMode;
    modeStartTime = millis();

    strip.clear();
    strip.show();

    Serial.print("Mode changed to: ");

    switch (newMode)
    {
        case MODE_IDLE:
            Serial.println("IDLE");
            break;

        case MODE_GESTURE:
            Serial.println("GESTURE");
            break;

        case MODE_WAITING:
            Serial.println("WAITING");
            break;

        case MODE_GENTLE:
            Serial.println("GENTLE");
            break;

        case MODE_MODERATE:
            Serial.println("MODERATE");
            break;

        case MODE_VIGOROUS:
            Serial.println("VIGOROUS");
            break;

        case MODE_ERROR:
            Serial.println("ERROR");
            break;
    }
}


// RGB 插值
uint32_t lerpColor(
    uint8_t r1,
    uint8_t g1,
    uint8_t b1,
    uint8_t r2,
    uint8_t g2,
    uint8_t b2,
    float t
)
{
    uint8_t r = r1 + (r2 - r1) * t;
    uint8_t g = g1 + (g2 - g1) * t;
    uint8_t b = b1 + (b2 - b1) * t;

    return strip.Color(r, g, b);
}


// 给颜色乘一个亮度系数
uint32_t scaleColor(uint32_t color, float brightness)
{
    uint8_t r = (uint8_t)(color >> 16);
    uint8_t g = (uint8_t)(color >> 8);
    uint8_t b = (uint8_t)color;

    r *= brightness;
    g *= brightness;
    b *= brightness;

    return strip.Color(r, g, b);
}


// ======================================================
// MODE_IDLE
// 青色呼吸灯
// 周期 2 秒
// ======================================================

void updateIdle()
{
    unsigned long now = millis();

    // 2000 ms 一个完整周期
    float phase =
        (now % 2000) / 2000.0f;

    // cos 实现平滑呼吸
    float breath =
        0.5f - 0.5f * cos(phase * 2.0f * PI);

    // 最暗 8%
    // 最亮 30%
    float brightness =
        0.02f + breath * 0.22f;

    uint32_t color =
        scaleColor(CYAN, brightness);

    for (int i = 0; i < LED_COUNT; i++)
    {
        strip.setPixelColor(i, color);
    }

    strip.show();
}


// ======================================================
// MODE_GESTURE
//
// 1、5、9、13 紫色
// 2、4、6、8、10、12、14、16 蓝色
// 3、7、11、15 青色
//
// 周期 1.5 秒
// ======================================================

void updateGesture()
{
    unsigned long elapsed = millis() - modeStartTime;

    // 1.5s 一个完整周期
    float phase = (elapsed % 1500) / 1500.0f;

    // 平滑亮灭，不是硬闪
    float pulse =
        0.15f + 0.45f *
        (0.5f - 0.5f * cos(phase * 2.0f * PI));

    for (int lamp = 1; lamp <= 16; lamp++)
    {
        uint32_t color;

        // 灯1、9：紫色
        if (lamp == 1 || lamp == 9)
        {
            color = strip.Color(140, 0, 220);
        }

        // 灯5、13：青色
        else if (lamp == 5 || lamp == 13)
        {
            color = strip.Color(0, 120, 140);
        }

        // 1 -> 5：紫 -> 青
        else if (lamp > 1 && lamp < 5)
        {
            float t = (lamp - 1) / 4.0f;

            color = lerpColor(
                140, 0, 220,
                0, 120, 140,
                t
            );
        }

        // 5 -> 9：青 -> 紫
        else if (lamp > 5 && lamp < 9)
        {
            float t = (lamp - 5) / 4.0f;

            color = lerpColor(
                0, 120, 140,
                140, 0, 220,
                t
            );
        }

        // 9 -> 13：紫 -> 青
        else if (lamp > 9 && lamp < 13)
        {
            float t = (lamp - 9) / 4.0f;

            color = lerpColor(
                140, 0, 220,
                0, 120, 140,
                t
            );
        }

        // 13 -> 16 -> 1：青 -> 紫
        else
        {
            float t = (lamp - 13) / 4.0f;

            color = lerpColor(
                0, 120, 140,
                140, 0, 220,
                t
            );
        }

        strip.setPixelColor(
            lamp - 1,
            scaleColor(color, pulse)
        );
    }

    strip.show();
}

// ======================================================
// 手势识别成功
// 整圈快速闪绿一次
// ======================================================

void gestureSuccess()
{
    strip.clear();

    for (int i = 0; i < LED_COUNT; i++)
    {
        strip.setPixelColor(
            i,
            strip.Color(0, 180, 0)
        );
    }

    strip.show();

    delay(250);

    strip.clear();
    strip.show();

    Serial.println("Gesture recording complete!");
}


// ======================================================
// MODE_WAITING
//
// 黄灯闪 3 次
// 一秒一次
//
// 3
// 2
// 1
//
// 结束后自动进入 GESTURE
// ======================================================

void updateWaiting()
{
    unsigned long elapsed = millis() - modeStartTime;

    // 3秒结束，自动进入手势识别模式
    if (elapsed >= 3000)
    {
        setMode(MODE_GESTURE);
        return;
    }

    // 每1秒一个周期
    unsigned long cycleTime = elapsed % 1000;

    // 前800ms转一圈，后200ms停顿
    const unsigned long rotateTime = 800;
    const unsigned long pauseTime  = 200;

    int head;

    if (cycleTime < rotateTime)
    {
        // 800ms内完成一整圈
        head = (cycleTime * LED_COUNT) / rotateTime;

        if (head >= LED_COUNT)
            head = LED_COUNT - 1;
    }
    else
    {
        // 后200ms停在最后一颗
        head = LED_COUNT - 1;
    }

    for (int i = 0; i < LED_COUNT; i++)
    {
        // 很暗的白色背景
        uint32_t color = strip.Color(6, 6, 6);

        // 与当前亮点的距离
        int distance =
            (head - i + LED_COUNT) % LED_COUNT;

        // 更偏绿色的黄绿色拖尾
        if (distance == 0)
        {
            color = strip.Color(35, 150, 5);
        }
        else if (distance == 1)
        {
            color = strip.Color(28, 110, 4);
        }
        else if (distance == 2)
        {
            color = strip.Color(20, 75, 3);
        }
        else if (distance == 3)
        {
            color = strip.Color(12, 45, 2);
        }
        else if (distance == 4)
        {
            color = strip.Color(6, 22, 1);
        }

        strip.setPixelColor(i, color);
    }

    strip.show();
}

// ======================================================
// 三色渐变
//
// 灯1  -> color1
// 灯5  -> color2
// 灯9  -> color3
// 灯13 -> color2
// 灯16 -> 接近 color1
//
// 整个灯环形成对称渐变
// ======================================================

void drawMusicGradient(
    uint8_t r1,
    uint8_t g1,
    uint8_t b1,

    uint8_t r2,
    uint8_t g2,
    uint8_t b2,

    uint8_t r3,
    uint8_t g3,
    uint8_t b3,

    float brightness
)
{
    for (int i = 0; i < 16; i++)
    {
        uint32_t color;

        // 灯1 ~ 灯5
        if (i <= 4)
        {
            float t = i / 4.0f;

            color = lerpColor(
                r1, g1, b1,
                r2, g2, b2,
                t
            );
        }

        // 灯5 ~ 灯9
        else if (i <= 8)
        {
            float t =
                (i - 4) / 4.0f;

            color = lerpColor(
                r2, g2, b2,
                r3, g3, b3,
                t
            );
        }

        // 灯9 ~ 灯13
        else if (i <= 12)
        {
            float t =
                (i - 8) / 4.0f;

            color = lerpColor(
                r3, g3, b3,
                r2, g2, b2,
                t
            );
        }

        // 灯13 ~ 灯16
        else
        {
            float t =
                (i - 12) / 4.0f;

            color = lerpColor(
                r2, g2, b2,
                r1, g1, b1,
                t
            );
        }

        strip.setPixelColor(
            i,
            scaleColor(
                color,
                brightness
            )
        );
    }

    strip.show();
}


// ======================================================
// 根据 BPM 计算节拍亮度
//
// 每一个 beat：
// 亮 -> 慢慢变暗
//
// 最暗 25%
// 最亮 75%
// ======================================================

float getBeatBrightness()
{
    float beatInterval =
        60000.0f / bpm;

    unsigned long elapsed =
        millis() - modeStartTime;

    float phase =
        fmod(elapsed, beatInterval)
        / beatInterval;

    float brightness;

    // 每拍开始亮一下，但整体压暗
    if (phase < 0.35f)
    {
        brightness = 0.50f - (phase / 0.35f) * 0.42f;
    }
    else
    {
        brightness = 0.08f;
    }

    return brightness;
}


// ======================================================
// MODE_GENTLE
//
// 蓝 -> 青 -> 绿
// ======================================================

void updateGentle()
{
    float brightness =
        getBeatBrightness();

    drawMusicGradient(
        0,   40, 180,     // 蓝
        0,   180, 90,    // 青
        0,   250, 0,     // 绿
        brightness
    );
}


// ======================================================
// MODE_MODERATE
//
// 品红 -> 紫 -> 蓝
// ======================================================

void updateModerate()
{
    float brightness =
        getBeatBrightness();

    drawMusicGradient(
        255, 0,   180,    // 品红
        150, 0,   255,    // 紫
        0,   60,  255,    // 蓝
        brightness
    );
}


// ======================================================
// MODE_VIGOROUS
//
// 红 -> 橙 -> 黄
// ======================================================

void updateVigorous()
{
    float brightness =
        getBeatBrightness();

    drawMusicGradient(
        255, 0,   0,      // 红
        255, 70,  0,      // 橙
        255, 220, 0,      // 黄
        brightness
    );
}


// ======================================================
// MODE_ERROR
//
// 红色快速闪两次
// 等待 3 秒
// 然后回到 IDLE
// ======================================================

void updateError()
{
    unsigned long elapsed =
        millis() - modeStartTime;

    // 150 + 150 + 150 + 150 = 600ms
    // 再等待 1500ms
    // 总周期 = 2100ms
    unsigned long cycleTime =
        elapsed % 2100;

    bool redOn = false;

    if (cycleTime < 150)
    {
        redOn = true;
    }
    else if (cycleTime < 300)
    {
        redOn = false;
    }
    else if (cycleTime < 450)
    {
        redOn = true;
    }
    else
    {
        redOn = false;
    }

    if (redOn)
    {
        for (int i = 0; i < LED_COUNT; i++)
        {
            strip.setPixelColor(
                i,
                scaleColor(RED, 0.45f)
            );
        }
    }
    else
    {
        strip.clear();
    }

    strip.show();
}

// ======================================================
// 串口指令
// ======================================================

void processSerial()
{
    if (!Serial.available())
        return;

    String command =
        Serial.readStringUntil('\n');

    command.trim();
    command.toUpperCase();

    Serial.print("Command: ");
    Serial.println(command);

    if (command == "IDLE")
    {
        setMode(MODE_IDLE);
    }

    else if (command == "GESTURE")
    {
        setMode(MODE_GESTURE);
    }

    else if (
        command == "GESTURE_OK" ||
        command == "OK"
    )
    {
        gestureSuccess();
    }

    else if (command == "WAITING")
    {
        setMode(MODE_WAITING);
    }

    else if (command == "GENTLE")
    {
        setMode(MODE_GENTLE);
    }

    else if (command == "MODERATE")
    {
        setMode(MODE_MODERATE);
    }

    else if (command == "VIGOROUS")
    {
        setMode(MODE_VIGOROUS);
    }

    else if (command == "ERROR")
    {
        setMode(MODE_ERROR);
    }

    // 支持修改 BPM
    // 例如：
    // BPM 120
    else if (command.startsWith("BPM "))
    {
        int newBpm =
            command.substring(4).toInt();

        if (
            newBpm >= 40 &&
            newBpm <= 240
        )
        {
            bpm = newBpm;

            Serial.print("BPM = ");
            Serial.println(bpm);
        }
        else
        {
            Serial.println(
                "BPM must be 40~240"
            );
        }
    }

    else
    {
        Serial.println(
            "Unknown command"
        );
    }
}


// ======================================================
// setup
// ======================================================

void setup()
{
    Serial.begin(115200);

    strip.begin();

    // 全局不限制
    // 各模式自己控制实际亮度
    strip.setBrightness(255);

    strip.clear();
    strip.show();

    delay(500);

    Serial.println();
    Serial.println(
        "===== 16 LED Music Ring ====="
    );

    Serial.println(
        "Commands:"
    );

    Serial.println("IDLE");
    Serial.println("WAITING");
    Serial.println("GESTURE");
    Serial.println("GESTURE_OK");
    Serial.println("GENTLE");
    Serial.println("MODERATE");
    Serial.println("VIGOROUS");
    Serial.println("ERROR");
    Serial.println("BPM 120");

    Serial.println();

    setMode(MODE_IDLE);
}


// ======================================================
// loop
// ======================================================

void loop()
{
    // 永远优先检测串口
    processSerial();

    switch (currentMode)
    {
        case MODE_IDLE:
            updateIdle();
            break;

        case MODE_GESTURE:
            updateGesture();
            break;

        case MODE_WAITING:
            updateWaiting();
            break;

        case MODE_GENTLE:
            updateGentle();
            break;

        case MODE_MODERATE:
            updateModerate();
            break;

        case MODE_VIGOROUS:
            updateVigorous();
            break;

        case MODE_ERROR:
            updateError();
            break;
    }

    delay(10);
}