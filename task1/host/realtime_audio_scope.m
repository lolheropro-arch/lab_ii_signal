function realtime_audio_scope(varargin)
% REALTIME_AUDIO_SCOPE  แสดง waveform / FFT / spectrogram แบบ real-time
%                       จาก sample block ที่ ESP32 ส่งมาทาง serial
%
%   ใช้ได้กับ Task 1, 2 และ 3 ตราบใดที่ ESP32 ส่ง frame รูปแบบเดียวกับ
%   task1_adc_mic.ino (ค่า Fs, N, ชนิด sample อ่านจาก header ของ frame เอง
%   จึงไม่ต้องแก้สคริปต์นี้เมื่อเปลี่ยน sampling rate หรือขนาด block)
%
% วิธีใช้
%   1) อัปโหลด sketch ลง ESP32 และ "ปิด Serial Monitor ของ Arduino IDE" ก่อน
%      (serial port เปิดได้ทีละโปรแกรม)
%   2) แก้ค่าในส่วน "ตั้งค่า" ข้างล่าง แล้วกด Run   หรือพิมพ์ใน Command Window:
%         realtime_audio_scope                          % เลือก port ให้อัตโนมัติ
%         realtime_audio_scope('port', 'COM5')          % Windows
%         realtime_audio_scope('port', '/dev/ttyUSB0')  % Linux
%         realtime_audio_scope('demo', true)            % ลองหน้าจอโดยไม่ต้องต่อบอร์ด
%   3) แถบด้านบน
%      ปุ่ม Stop/Play  : หยุดภาพค้างไว้ดู/จับภาพ แล้วกดอีกครั้งเพื่อรับข้อมูลต่อ
%                        (ตอนหยุดยังเปลี่ยน window / หน่วย / ขอบเขตแกนได้ กราฟจะวาดใหม่ทันที)
%      เมนู FFT window : เลือก window function ที่ใช้ก่อนทำ FFT
%      Overlay FFT without window : วาดสเปกตรัมแบบไม่ใส่ window ซ้อนไว้เทียบ
%                                   (ใช้ดู spectral leakage ตามข้อ 5.2 ของโจทย์)
%   4) แผง "Axis settings" ด้านขวา  ตั้งได้ทุกกราฟ ทั้งแกนนอน (X) แกนตั้ง (Y)
%      และแถบสี (Color) ของ spectrogram
%        Min / Max : ขอบเขตของแกน      Step : ระยะห่างของขีดบนแกน
%        Unit      : หน่วยของแกน  (FFT เลือกได้ dBFS / dBV / Amplitude (V))
%      - ตอนเริ่มโปรแกรมทุกแถวติ๊ก Auto ไว้ : โปรแกรมเลือกขอบเขตเอง และช่อง Min/Max/Step
%        แสดงค่าที่กราฟใช้อยู่จริง (พื้นช่องสีเดียวกับแผง)
%      - จะกำหนดเอง : พิมพ์ตัวเลขทับในช่องแล้วกด Enter  แถวนั้นจะเอาติ๊ก Auto ออกให้เอง
%        (พื้นช่องเปลี่ยนเป็นสีขาว) ช่องอื่นในแถวคงค่าที่แสดงอยู่ตอนนั้นไว้
%        ตัวเลขเป็นหน่วยที่เลือกในช่อง Unit ของแถวนั้น  (เว้นช่องว่าง = ใช้ค่า auto ของช่องนั้น)
%      - ติ๊ก Auto กลับ = กลับไปให้โปรแกรมเลือกเอง
%      - เปลี่ยน Unit แล้วแถวนั้นจะกลับเป็น Auto เพราะเลขเดิมเป็นหน่วยเก่า
%   5) ปิดหน้าต่างเพื่อเลิกใช้งาน (port จะถูกปล่อยให้อัตโนมัติ)
%
% หน่วยของแกน
%   dBFS          : เทียบกับ sine ที่เต็มช่วง ADC (0 dBFS = เต็มช่วงพอดี)
%   dBV           : เทียบกับ 1 V rms     ต้องตั้ง cfg.adcFullScaleVolts ให้ตรงกับบอร์ด
%   Amplitude (V) : amplitude แบบ peak ของแต่ละความถี่ หน่วย V (ใช้ cfg.adcFullScaleVolts เช่นกัน)
%   (Task 2 ไมค์ I2S ส่งค่าดิจิทัลมาเลย ไม่มีแรงดันให้เทียบ ให้ใช้ dBFS)
%
% ชื่อ serial port
%   Windows : COM3, COM5, ...  ดูใน Device Manager > Ports (COM & LPT)
%   Linux   : /dev/ttyUSB0 หรือ /dev/ttyACM0   ดูด้วย  ls /dev/ttyUSB* /dev/ttyACM*
%             ถ้าขึ้น permission denied ให้รัน  sudo usermod -aG dialout $USER
%             แล้ว logout/login ใหม่
%   ดูรายชื่อ port จากใน MATLAB ได้ด้วยคำสั่ง  serialportlist("available")
%
% ไม่ต้องใช้ toolbox เพิ่ม (window function, spectrogram และ colormap inferno อยู่ในไฟล์นี้)
% ต้องใช้ MATLAB R2019b ขึ้นไป (ใช้ serialport)

% =========================================================================
%  >>>>>>>>>>>>>>>>>>>>>>   ส่วนตั้งค่า (แก้ตรงนี้)   <<<<<<<<<<<<<<<<<<<<<<
% =========================================================================

% ชื่อ serial port   '' = ให้สคริปต์เลือกเอง (ใช้ได้เมื่อมีบอร์ดเสียบอยู่ตัวเดียว)
cfg.port = '';

% Baud rate  ต้องตรงกับ SERIAL_BAUD ใน sketch
cfg.baud = 1000000;

% true = ใช้สัญญาณจำลอง (1 kHz + 2.5 kHz) แทนบอร์ดจริง ไว้ลองหน้าจอ
cfg.demo = false;

% Window ที่เลือกไว้ตอนเปิดโปรแกรม (เปลี่ยนระหว่างรันได้จากเมนูบนหน้าจอ)
%   'Rectangular (no window)', 'Hann', 'Hamming', 'Blackman', 'Flat-top'
cfg.window = 'Hann';

% สถานะเริ่มต้นของ checkbox "Overlay FFT without window"
cfg.overlayNoWindow = false;

% แรงดัน (V) ที่ทำให้ ADC อ่านได้ค่าสูงสุด (4095 สำหรับ 12 บิต)  ใช้แปลงเป็น V / dBV
% ESP32-S3 ตั้ง ADC_11db ได้ประมาณ 3.1 V  ถ้าต้องการให้แม่นให้วัดเทียบกับ oscilloscope แล้วแก้ค่านี้
cfg.adcFullScaleVolts = 3.1;

% ช่วงแกน dB เริ่มต้นของ FFT และ spectrogram  หน่วย dBFS  (เปลี่ยนบนหน้าจอได้)
cfg.dbRange = [-100 0];

% spectrogram แสดงย้อนหลังกี่วินาที
cfg.spectroSeconds = 5;

% จำนวนยอดความถี่ (dominant peak) สูงสุดที่ติดป้ายบนกราฟ FFT
cfg.maxPeaks = 3;

% ติดป้ายเฉพาะยอดที่สูงกว่าระดับนี้ (dBFS)  กันไม่ให้ติดป้ายที่ noise ตอนเงียบ
cfg.peakMinDb = -60;

% สีของหน้าจอ  [R G B] ค่า 0..1
cfg.colors.figure  = [0.753 0.753 0.753];   % พื้นหลังหน้าต่าง : silver gray (#C0C0C0)
cfg.colors.axes    = [0.847 0.847 0.847];   % พื้นหลังกราฟ   : light silver (#D8D8D8)
cfg.colors.text    = [0.07 0.07 0.07];      % ตัวอักษร / เส้นแกน
cfg.colors.grid    = [0.30 0.30 0.30];      % เส้น grid
cfg.colors.edit    = [0.96 0.96 0.96];      % ช่องกรอกตัวเลข
cfg.colors.signal  = [0.00 0.30 0.65];      % เส้นสัญญาณหลัก (น้ำเงินเข้ม)
cfg.colors.compare = [0.76 0.25 0.05];      % เส้น FFT แบบไม่ใส่ window (ส้มเข้ม)

% หยุดเองหลังรับครบกี่ block   inf = รันไปเรื่อย ๆ จนกว่าจะปิดหน้าต่าง
cfg.maxBlocks = inf;

% =========================================================================
%  จบส่วนตั้งค่า
% =========================================================================

for k = 1:2:numel(varargin)                     % ค่าที่ส่งมาตอนเรียกฟังก์ชันจะทับค่าข้างบน
    cfg.(varargin{k}) = varargin{k + 1};
end

WINDOW_NAMES = {'Rectangular (no window)', 'Hann', 'Hamming', 'Blackman', 'Flat-top'};

h = buildGui(cfg, WINDOW_NAMES);

% ---- เปิด serial port ---------------------------------------------------
sp = [];
if cfg.demo
    sourceName = 'DEMO (simulated data)';
else
    port = pickPort(cfg.port);
    sp = serialport(port, cfg.baud);
    % ปล่อยสาย DTR/RTS ทั้งคู่ ไม่อย่างนั้นวงจร auto-reset บนบอร์ดอาจค้าง ESP32 ไว้ในสถานะ reset
    setDTR(sp, false);
    setRTS(sp, false);
    pause(0.5);
    flush(sp);
    sourceName = sprintf('%s @ %d baud', port, cfg.baud);
end
set(h.fig, 'Name', ['Real-time audio scope - ' sourceName]);

% ---- ตัวแปรสถานะ --------------------------------------------------------
rx        = zeros(1, 0, 'uint8');   % byte ที่รับมาแล้วแต่ยังแยก frame ไม่ครบ
layout    = [0 0 0 0];              % [fs n bits isSigned] ที่ตั้งไว้ล่าสุด
S         = [];                     % ข้อมูล spectrogram (ความถี่ x เวลา) หน่วย dBFS
d         = [];                     % block ล่าสุด + ตัวนับ (ใช้วาดซ้ำตอนกด Stop)
lastSeq   = -1;
nBlocks   = 0;
totMissed = 0;                      % sample ที่ ESP32 อ่าน ADC ไม่ทัน (นับจาก header)
totDrop   = 0;                      % block ที่หายระหว่างทาง (ดูจากเลข seq กระโดด)
totBad    = 0;                      % frame ที่ header/checksum ไม่ถูกต้อง
demoSeq   = 0;

try
    while ishghandle(h.fig) && nBlocks < cfg.maxBlocks
        playing = get(h.btn, 'Value') == 1;

        % ---- 1) อ่าน byte ที่มาถึงแล้ว ---------------------------------
        if cfg.demo
            if playing
                 [newBytes, blockTime] = demoFrame(demoSeq);
                demoSeq = demoSeq + 1;
                pause(blockTime);
            else
                newBytes = zeros(1, 0, 'uint8');
            end
        else
            nAvail = sp.NumBytesAvailable;
            if nAvail > 0
                newBytes = uint8(read(sp, nAvail, 'uint8'));
                newBytes = newBytes(:).';
            else
                newBytes = zeros(1, 0, 'uint8');
                pause(0.005);
            end
        end

        % ---- 2) ตอนกด Stop : ทิ้งข้อมูลที่เข้ามา แต่ยังวาด block สุดท้ายใหม่ได้
        %         (เผื่อผู้ใช้เปลี่ยน window / หน่วย / ขอบเขตแกนระหว่างหยุด)
        if ~playing
            rx = zeros(1, 0, 'uint8');
            lastSeq = -1;
            if ~isempty(d)
                drawAll(h, cfg, d, WINDOW_NAMES);
            end
            drawnow;
            pause(0.05);
            continue;
        end

        % ---- 3) แยก frame ออกจาก byte stream ---------------------------
        rx = [rx, newBytes]; %#ok<AGROW>
        [frames, rx, nBad] = parseFrames(rx);
        totBad = totBad + nBad;
        if isempty(frames)
            drawnow;
            continue;
        end

        % ---- 4) ทุก frame ต้องเข้า spectrogram ---------------------------
        winName = WINDOW_NAMES{get(h.pop, 'Value')};
        for i = 1:numel(frames)
            fr = frames(i);
            newLayout = [fr.fs, fr.n, fr.bits, fr.isSigned];
            if ~isequal(newLayout, layout)
                layout = newLayout;
                nCols = max(2, ceil(cfg.spectroSeconds * fr.fs / fr.n));
                S = cfg.dbRange(1) * ones(floor(fr.n / 2) + 1, nCols);
            end
            if lastSeq >= 0 && fr.seq > lastSeq + 1
                totDrop = totDrop + (fr.seq - lastSeq - 1);
            end
            lastSeq   = fr.seq;
            totMissed = totMissed + fr.missed;
            nBlocks   = nBlocks + 1;

            [~, amp] = spectrumAmp(fr.x, fr.fs, makeWindow(winName, fr.n));
            S = [S(:, 2:end), toDbfs(amp, fr.bits)];
        end

        % ---- 5) วาดกราฟจาก frame ล่าสุด --------------------------------
        d = struct('fr', fr, 'S', S, 'nBlocks', nBlocks, 'totMissed', totMissed, ...
                   'totDrop', totDrop, 'totBad', totBad);
        drawAll(h, cfg, d, WINDOW_NAMES);
        drawnow;
    end
catch err
    % ปิดหน้าต่างระหว่างที่กำลังวาด = เลิกใช้งานตามปกติ ไม่ต้องแจ้ง error
    if ishghandle(h.fig)
        clear sp
        rethrow(err);
    end
end

clear sp                                        % ปล่อย serial port
end

% =========================================================================
%  วาดกราฟทั้งหมดจาก block ล่าสุด ตามหน่วยและขอบเขตแกนที่ผู้ใช้เลือก
% =========================================================================
function drawAll(h, cfg, d, windowNames)
fr = d.fr;
n  = fr.n;
fs = fr.fs;
fullScale = 2 ^ (fr.bits - 1);                      % amplitude ของ sine ที่เต็มช่วง ADC
kV   = cfg.adcFullScaleVolts / (2 ^ fr.bits - 1);   % แรงดันต่อ 1 count
offV = 20 * log10(fullScale * kV / sqrt(2));        % dBV = dBFS + offV
winName = windowNames{get(h.pop, 'Value')};

% ---------------- Waveform ----------------
switch unitOf(h.ctl.wave.x)
    case 's',       tx = (0:n - 1).' / fs;          tEnd = n / fs;        xLab = 'Time (s)';
    case 'samples', tx = (0:n - 1).';               tEnd = n - 1;         xLab = 'Sample index';
    otherwise,      tx = (0:n - 1).' * 1000 / fs;   tEnd = n * 1000 / fs; xLab = 'Time (ms)';
end
if strcmp(unitOf(h.ctl.wave.y), 'V')
    yw = fr.x * kV;  yLab = 'Voltage (V)';
else
    yw = fr.x;       yLab = 'Sample value (ADC counts)';
end
set(h.lineWave, 'XData', tx, 'YData', yw);
applyAxis(h.axWave, 'X', h.ctl.wave.x, [0, tEnd]);
applyAxis(h.axWave, 'Y', h.ctl.wave.y, niceRange(min(yw), max(yw)));
setAxText(h.axWave, 'XLabel', xLab);
setAxText(h.axWave, 'YLabel', yLab);
setAxText(h.axWave, 'Title', sprintf('Waveform  (block #%d)', fr.seq));

% ---------------- FFT ----------------
[f, amp] = spectrumAmp(fr.x, fs, makeWindow(winName, n));
dBFS = toDbfs(amp, fr.bits);
fUnit = unitOf(h.ctl.fft.x);
fScale = 1;
if strcmp(fUnit, 'kHz'), fScale = 1e-3; end
fx = f * fScale;

magUnit = unitOf(h.ctl.fft.y);
[yv, defY, magLab] = convertMag(amp, dBFS, magUnit, kV, offV, cfg);
set(h.lineWin, 'XData', fx, 'YData', yv);

showOverlay = get(h.chkOverlay, 'Value') == 1;
if showOverlay
    [~, ampR] = spectrumAmp(fr.x, fs, ones(n, 1));
    [yR, defR] = convertMag(ampR, toDbfs(ampR, fr.bits), magUnit, kV, offV, cfg);
    set(h.lineRect, 'XData', fx, 'YData', yR);
    defY = [min(defY(1), defR(1)), max(defY(2), defR(2))];
end
set(h.lineRect, 'Visible', onOff(showOverlay));
set(h.leg,      'Visible', onOff(showOverlay));

applyAxis(h.axFft, 'X', h.ctl.fft.x, [0, fs / 2] * fScale);
applyAxis(h.axFft, 'Y', h.ctl.fft.y, defY);
setAxText(h.axFft, 'XLabel', sprintf('Frequency (%s)', fUnit));
setAxText(h.axFft, 'YLabel', magLab);

% ยอดความถี่เด่น (หาใน dBFS เสมอ แล้วแสดงในหน่วยที่เลือก)
pk = topPeaks(dBFS, numel(h.pkTxt), 6, 30, cfg.peakMinDb);
set(h.linePk, 'XData', fx(pk), 'YData', yv(pk));
yl = get(h.axFft, 'YLim');
peakStr = '';
for j = 1:numel(h.pkTxt)
    if j <= numel(pk)
        fStr = formatFreq(f(pk(j)), fUnit);
        set(h.pkTxt{j}, 'Position', [fx(pk(j)), yv(pk(j)) + 0.05 * diff(yl), 0], ...
            'String', fStr, 'Visible', 'on');
        peakStr = [peakStr, sprintf('%s (%s)   ', fStr, formatMag(yv(pk(j)), magUnit))]; %#ok<AGROW>
    else
        set(h.pkTxt{j}, 'Visible', 'off');
    end
end
if isempty(peakStr), peakStr = 'none'; end
setAxText(h.axFft, 'Title', sprintf('FFT   |   window: %s   |   peaks: %s', winName, peakStr));

% ---------------- Spectrogram ----------------
tb    = n / fs;                                 % เวลาของ 1 block
nCols = size(d.S, 2);
tScale = 1;
if strcmp(unitOf(h.ctl.spec.x), 'ms'), tScale = 1000; end
sfUnit = unitOf(h.ctl.spec.y);
sfScale = 1;
if strcmp(sfUnit, 'kHz'), sfScale = 1e-3; end
cUnit = unitOf(h.ctl.spec.c);
cOff = 0;
if strcmp(cUnit, 'dBV'), cOff = offV; end

set(h.img, 'CData', d.S + cOff, ...
    'XData', [-(nCols - 0.5) * tb, -0.5 * tb] * tScale, 'YData', [0, fs / 2] * sfScale);
applyAxis(h.axSpec, 'X', h.ctl.spec.x, [-nCols * tb, 0] * tScale);
applyAxis(h.axSpec, 'Y', h.ctl.spec.y, [0, fs / 2] * sfScale);
applyAxis(h.axCb,   'Y', h.ctl.spec.c, cfg.dbRange + cOff);
cl = get(h.axCb, 'YLim');
set(h.axSpec, 'CLim', cl);
set(h.axCb,   'CLim', cl);
set(h.imgCb,  'YData', cl, 'CData', linspace(cl(1), cl(2), 256).');
setAxText(h.axSpec, 'XLabel', sprintf('Time (%s, 0 = now)', unitOf(h.ctl.spec.x)));
setAxText(h.axSpec, 'YLabel', sprintf('Frequency (%s)', sfUnit));
setAxText(h.axCb,   'YLabel', cUnit);

% ---------------- แถบสถานะ ----------------
set(h.status, 'String', sprintf(['Fs = %d Hz   N = %d   df = %.2f Hz   blocks: %d   ', ...
    'mean = %.1f   peak-to-peak = %d   missed samples: %d   dropped blocks: %d   bad frames: %d'], ...
    fs, n, fs / n, d.nBlocks, mean(fr.x), max(fr.x) - min(fr.x), ...
    d.totMissed, d.totDrop, d.totBad));
end

% แปลง amplitude (หน่วย ADC count) เป็นหน่วยที่เลือกของแกน FFT
function [y, defLim, label] = convertMag(amp, dBFS, unit, kV, offV, cfg)
switch unit
    case 'dBV'
        y = dBFS + offV;
        defLim = cfg.dbRange + [0 15] + offV;
        label = 'Magnitude (dBV)';
    case 'Amplitude (V)'
        y = amp * kV;
        defLim = niceRange(0, max(1.15 * max(y), 1e-6));
        label = 'Amplitude (V peak)';
    otherwise
        y = dBFS;
        defLim = cfg.dbRange + [0 15];
        label = 'Magnitude (dBFS)';
end
end

function s = formatMag(v, unit)
switch unit
    case 'dBV',           s = sprintf('%.1f dBV', v);
    case 'Amplitude (V)', s = sprintf('%.4f V', v);
    otherwise,            s = sprintf('%.1f dBFS', v);
end
end

function s = formatFreq(fHz, unit)
if strcmp(unit, 'kHz')
    s = sprintf('%.3f kHz', fHz / 1000);
else
    s = sprintf('%.1f Hz', fHz);
end
end

% ตั้งขอบเขตและขีดของแกน
%   Auto ติ๊กอยู่ : ใช้ค่า default แล้วเขียนค่าที่ใช้จริงลงช่อง Min / Max / Step ให้เห็น
%   Auto ไม่ติ๊ก : ใช้ค่าที่ผู้ใช้กรอก  (ช่องว่าง หรือ Min >= Max -> ใช้ค่า default แทน)
function applyAxis(ax, which, ctl, defLim)
if get(ctl.auto, 'Value') == 1
    set(ax, [which 'Lim'], defLim);
    set(ax, [which 'TickMode'], 'auto');
    tk = get(ax, [which 'Tick']);
    st = NaN;
    if numel(tk) >= 2, st = tk(2) - tk(1); end
    setIfChanged(ctl.min,  fmtNum(defLim(1)));
    setIfChanged(ctl.max,  fmtNum(defLim(2)));
    setIfChanged(ctl.step, fmtNum(st));
    return;
end
lo = str2double(get(ctl.min,  'String'));
hi = str2double(get(ctl.max,  'String'));
st = str2double(get(ctl.step, 'String'));
if isnan(lo), lo = defLim(1); end
if isnan(hi), hi = defLim(2); end
if ~(hi > lo)                               % ค่าที่กรอกขัดกัน (Min >= Max) -> ใช้ default
    lo = defLim(1);
    hi = defLim(2);
end
set(ax, [which 'Lim'], [lo, hi]);
if ~isnan(st) && st > 0 && (hi - lo) / st <= 100
    set(ax, [which 'Tick'], (ceil(lo / st - 1e-9):floor(hi / st + 1e-9)) * st);
else
    set(ax, [which 'TickMode'], 'auto');
end
end

% ตัวเลขสำหรับแสดงในช่อง : ค่าตั้งแต่ 1000 ขึ้นไปปัดเป็นจำนวนเต็ม นอกนั้นใช้ 4 หลักสำคัญ
function s = fmtNum(v)
if isnan(v)
    s = '';
    return;
end
if abs(v) < 1e-12, v = 0; end
if abs(v) >= 1000
    s = sprintf('%.0f', v);
else
    s = sprintf('%.4g', v);
end
end

% เขียนลงช่องเฉพาะตอนที่ค่าเปลี่ยน (ไม่ให้ช่องกระพริบ)
function setIfChanged(hEdit, str)
if ~strcmp(get(hEdit, 'String'), str)
    set(hEdit, 'String', str);
end
end

% ขอบเขต auto ที่ปัดออกเป็นเลขกลม ๆ (1, 2, 5 x 10^k)  ค่าจึงไม่เปลี่ยนทุก block
function r = niceRange(lo, hi)
if hi <= lo
    r = [lo - 1, hi + 1];
    return;
end
raw = (hi - lo) / 5;
p = 10 ^ floor(log10(raw));
m = raw / p;
if m <= 1, st = p; elseif m <= 2, st = 2 * p; elseif m <= 5, st = 5 * p; else, st = 10 * p; end
r = [floor(lo / st) * st, ceil(hi / st) * st];
end

function u = unitOf(ctl)
list = get(ctl.unit, 'String');
u = list{get(ctl.unit, 'Value')};
end

function setAxText(ax, prop, str)
set(get(ax, prop), 'String', str);
end

function s = onOff(tf)
if tf, s = 'on'; else, s = 'off'; end
end

% =========================================================================
%  สร้างหน้าจอ
% =========================================================================
function h = buildGui(cfg, windowNames)
C = cfg.colors;
h.fig = figure('Name', 'Real-time audio scope', 'NumberTitle', 'off', ...
    'Color', C.figure, 'Units', 'normalized', 'Position', [0.04 0.05 0.92 0.88]);
try
    theme(h.fig, 'light');          % MATLAB R2025a ขึ้นไป : ไม่ให้ dark theme ทับสีที่ตั้งไว้
catch
end

ui = {'BackgroundColor', C.figure, 'ForegroundColor', C.text, 'Units', 'normalized'};

% ---- แถบควบคุมด้านบน ----
h.btn = uicontrol(h.fig, 'Style', 'togglebutton', 'String', 'Stop', 'Value', 1, ...
    'Units', 'normalized', 'Position', [0.015 0.945 0.075 0.04], 'FontWeight', 'bold', ...
    'ForegroundColor', C.text, 'BackgroundColor', [0.80 0.90 0.80], 'Callback', @onPlayStop);

uicontrol(h.fig, 'Style', 'text', 'String', 'FFT window:', ui{:}, ...
    'Position', [0.10 0.943 0.07 0.03], 'HorizontalAlignment', 'right');

initial = find(strcmpi(windowNames, cfg.window), 1);
if isempty(initial), initial = 2; end
h.pop = uicontrol(h.fig, 'Style', 'popupmenu', 'String', windowNames, 'Value', initial, ...
    'Units', 'normalized', 'Position', [0.175 0.945 0.15 0.035], ...
    'BackgroundColor', C.edit, 'ForegroundColor', C.text);

h.chkOverlay = uicontrol(h.fig, 'Style', 'checkbox', 'String', 'Overlay FFT without window', ...
    'Value', double(cfg.overlayNoWindow), ui{:}, 'Position', [0.345 0.945 0.20 0.035]);

h.status = uicontrol(h.fig, 'Style', 'text', 'String', 'Waiting for data ...', ui{:}, ...
    'Position', [0.015 0.005 0.72 0.03], 'HorizontalAlignment', 'left');

% ---- กราฟ 3 ช่อง ----
AX_X = 0.055;  AX_W = 0.63;

h.axWave = axes('Parent', h.fig, 'Position', [AX_X 0.69 AX_W 0.19]);
styleAxes(h.axWave, C);
h.lineWave = line('Parent', h.axWave, 'XData', [0 1], 'YData', [0 0], 'Color', C.signal);
setAxText(h.axWave, 'Title', 'Waveform');

h.axFft = axes('Parent', h.fig, 'Position', [AX_X 0.39 AX_W 0.19]);
styleAxes(h.axFft, C);
h.lineRect = line('Parent', h.axFft, 'XData', [0 1], 'YData', [0 0], 'Color', C.compare, 'Visible', 'off');
h.lineWin  = line('Parent', h.axFft, 'XData', [0 1], 'YData', [0 0], 'Color', C.signal, 'LineWidth', 1);
h.linePk   = line('Parent', h.axFft, 'XData', 0, 'YData', 0, 'LineStyle', 'none', ...
    'Marker', 'v', 'MarkerSize', 7, 'MarkerFaceColor', C.text, 'MarkerEdgeColor', C.text);
h.pkTxt = cell(1, cfg.maxPeaks);
for j = 1:cfg.maxPeaks
    h.pkTxt{j} = text(0, 0, '', 'Parent', h.axFft, 'Color', C.text, 'FontSize', 9, ...
        'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', ...
        'Clipping', 'on', 'Visible', 'off');
end
setAxText(h.axFft, 'Title', 'FFT');
h.leg = legend(h.axFft, [h.lineWin, h.lineRect], ...
    {'With selected window', 'No window (rectangular)'}, 'Location', 'northeast');
set(h.leg, 'Visible', 'off', 'Color', C.axes, 'TextColor', C.text, 'EdgeColor', C.grid);

h.axSpec = axes('Parent', h.fig, 'Position', [AX_X 0.09 AX_W 0.19]);
styleAxes(h.axSpec, C);
grid(h.axSpec, 'off');
h.img = image('Parent', h.axSpec, 'XData', [-1 0], 'YData', [0 1], ...
    'CData', cfg.dbRange(1) * ones(2, 2), 'CDataMapping', 'scaled');
set(h.axSpec, 'YDir', 'normal', 'CLim', cfg.dbRange, 'Layer', 'top');
colormap(h.axSpec, infernoMap());
setAxText(h.axSpec, 'Title', sprintf('Spectrogram (last %g s)', cfg.spectroSeconds));

% แถบสีของ spectrogram (วาดเองเพื่อให้ตำแหน่งคงที่ ไม่ไปเบียดกราฟ)
h.axCb = axes('Parent', h.fig, 'Position', [AX_X + AX_W + 0.008, 0.09, 0.011, 0.19]);
h.imgCb = image('Parent', h.axCb, 'XData', [0 1], 'YData', cfg.dbRange, ...
    'CData', linspace(cfg.dbRange(1), cfg.dbRange(2), 256).', 'CDataMapping', 'scaled');
styleAxes(h.axCb, C);
grid(h.axCb, 'off');
set(h.axCb, 'YDir', 'normal', 'CLim', cfg.dbRange, 'XLim', [0 1], 'YLim', cfg.dbRange, ...
    'XTick', [], 'YAxisLocation', 'right', 'Layer', 'top');
colormap(h.axCb, infernoMap());

% ---- แผงตั้งค่าแกน (ด้านขวา) ----
pnl = uipanel('Parent', h.fig, 'Title', 'Axis settings', 'Units', 'normalized', ...
    'Position', [0.735 0.05 0.255 0.88], 'BackgroundColor', C.figure, ...
    'ForegroundColor', C.text, 'FontWeight', 'bold');
uicontrol(pnl, 'Style', 'text', ui{:}, 'Position', [0.03 0.905 0.94 0.085], ...
    'HorizontalAlignment', 'left', 'String', ...
    {'Auto ticked: automatic, boxes show the values in use.', ...
     'Type a value + Enter to set it (Auto unticks itself).', ...
     'Tick Auto again, or change the Unit, to go back to Auto.'});
h.ctl.wave = axisGroup(pnl, [0.03 0.62 0.94 0.27], 'Waveform', {'X', 'Y'}, ...
    {{'ms', 's', 'samples'}, {'ADC counts', 'V'}}, C);
h.ctl.fft  = axisGroup(pnl, [0.03 0.335 0.94 0.27], 'FFT', {'X', 'Y'}, ...
    {{'Hz', 'kHz'}, {'dBFS', 'dBV', 'Amplitude (V)'}}, C);
h.ctl.spec = axisGroup(pnl, [0.03 0.01 0.94 0.31], 'Spectrogram', {'X', 'Y', 'Color'}, ...
    {{'s', 'ms'}, {'Hz', 'kHz'}, {'dBFS', 'dBV'}}, C);
end

% กลุ่มช่องกรอกของ 1 กราฟ : แต่ละแถว = [ชื่อแกน] [Auto] [Min] [Max] [Step] [Unit]
function g = axisGroup(parent, pos, titleStr, rowNames, unitLists, C)
p = uipanel('Parent', parent, 'Title', titleStr, 'Units', 'normalized', 'Position', pos, ...
    'BackgroundColor', C.figure, 'ForegroundColor', C.text, 'FontWeight', 'bold');
ui    = {'Units', 'normalized', 'ForegroundColor', C.text};
cols  = [0.01 0.10; 0.11 0.08; 0.20 0.16; 0.37 0.16; 0.54 0.12; 0.67 0.32];  % [x w] ของแต่ละคอลัมน์
heads = {'', 'Auto', 'Min', 'Max', 'Step', 'Unit'};
nR    = numel(rowNames);
rowH  = 1 / (nR + 1);
for c = 2:numel(heads)
    uicontrol(p, 'Style', 'text', 'String', heads{c}, ui{:}, 'BackgroundColor', C.figure, ...
        'Position', [cols(c, 1), 1 - 0.85 * rowH, cols(c, 2), 0.6 * rowH]);
end
g = struct();
for r = 1:nR
    y = 1 - (r + 1) * rowH + 0.2 * rowH;
    hgt = 0.6 * rowH;
    uicontrol(p, 'Style', 'text', 'String', rowNames{r}, ui{:}, 'BackgroundColor', C.figure, ...
        'FontWeight', 'bold', 'Position', [cols(1, 1), y, cols(1, 2), hgt * 0.85]);
    % ช่อง Min/Max/Step : ตอน Auto โปรแกรมเติมค่าที่ใช้จริงให้ (พื้นสีเดียวกับแผง)
    %                     พิมพ์ทับแล้วกด Enter = กำหนดเอง (พื้นสีขาว)
    edArgs = [ui, {'Style', 'edit', 'String', '', 'BackgroundColor', C.figure, ...
        'Callback', @onEditCommit}];
    e1 = uicontrol(p, edArgs{:}, 'Position', [cols(3, 1), y, cols(3, 2), hgt]);
    e2 = uicontrol(p, edArgs{:}, 'Position', [cols(4, 1), y, cols(4, 2), hgt]);
    e3 = uicontrol(p, edArgs{:}, 'Position', [cols(5, 1), y, cols(5, 2), hgt]);
    ck = uicontrol(p, 'Style', 'checkbox', 'String', '', 'Value', 1, ui{:}, ...
        'BackgroundColor', C.figure, 'Position', [cols(2, 1) + 0.025, y, 0.05, hgt], ...
        'Callback', @onAutoToggle);
    pu = uicontrol(p, 'Style', 'popupmenu', 'String', unitLists{r}, 'Value', 1, ui{:}, ...
        'BackgroundColor', C.edit, 'Position', [cols(6, 1), y, cols(6, 2), hgt], ...
        'Callback', @onUnitChange);
    % ข้อมูลของแถวนี้ ให้ callback ทุกตัวในแถวใช้ร่วมกัน
    rowInfo = struct('eds', {{e1, e2, e3}}, 'ck', ck, 'bgManual', C.edit, 'bgAuto', C.figure);
    rowObjs = {e1, e2, e3, ck, pu};
    for k = 1:numel(rowObjs)
        set(rowObjs{k}, 'UserData', rowInfo);
    end
    key = lower(rowNames{r}(1));                % 'x', 'y', 'c'
    g.(key) = struct('min', e1, 'max', e2, 'step', e3, 'unit', pu, 'auto', ck);
end
end

function styleAxes(ax, C)
set(ax, 'Color', C.axes, 'XColor', C.text, 'YColor', C.text, 'GridColor', C.grid, ...
    'GridAlpha', 0.35, 'FontSize', 9, 'LineWidth', 0.75, 'Box', 'on');
grid(ax, 'on');
set(get(ax, 'Title'),  'Color', C.text, 'FontWeight', 'bold');
set(get(ax, 'XLabel'), 'Color', C.text);
set(get(ax, 'YLabel'), 'Color', C.text);
end

% พิมพ์ค่าในช่องแล้วกด Enter -> แถวนั้นเป็นแบบกำหนดเอง (เอาติ๊ก Auto ออก)
function onEditCommit(src, ~)
row = get(src, 'UserData');
set(row.ck, 'Value', 0);
paintRow(row, true);
end

% ติ๊ก Auto = โปรแกรมเลือกค่าเอง, เอาติ๊กออก = ใช้ค่าที่แสดงอยู่ในช่องเป็นค่ากำหนดเอง
function onAutoToggle(src, ~)
paintRow(get(src, 'UserData'), get(src, 'Value') == 0);
end

% เปลี่ยนหน่วยแล้วแถวนั้นกลับเป็น Auto (เลขเดิมเป็นหน่วยเก่า)
function onUnitChange(src, ~)
row = get(src, 'UserData');
set(row.ck, 'Value', 1);
paintRow(row, false);
end

% สีพื้นของช่อง : ขาว = กำหนดเอง, สีเดียวกับแผง = Auto
function paintRow(row, manual)
if manual, bg = row.bgManual; else, bg = row.bgAuto; end
for k = 1:numel(row.eds)
    set(row.eds{k}, 'BackgroundColor', bg);
end
end

% ปุ่ม Stop/Play : Value = 1 กำลังรับข้อมูล (ปุ่มเขียนว่า Stop), Value = 0 หยุดอยู่ (ปุ่มเขียนว่า Play)
function onPlayStop(src, ~)
if get(src, 'Value') == 1
    set(src, 'String', 'Stop', 'BackgroundColor', [0.80 0.90 0.80]);
else
    set(src, 'String', 'Play', 'BackgroundColor', [0.96 0.82 0.72]);
end
end

% Colormap "inferno" (เหมือนของ matplotlib) 256 ระดับ  สร้างจากจุดอ้างอิง 33 จุด
function map = infernoMap()
anchors = [ ...
    0.0015 0.0005 0.0139; 0.0140 0.0112 0.0719; 0.0423 0.0281 0.1411
    0.0820 0.0433 0.2153; 0.1293 0.0473 0.2908; 0.1834 0.0403 0.3550
    0.2383 0.0366 0.3964; 0.2908 0.0456 0.4186; 0.3415 0.0623 0.4294
    0.3915 0.0809 0.4331; 0.4412 0.0993 0.4316; 0.4910 0.1172 0.4256
    0.5409 0.1347 0.4151; 0.5907 0.1526 0.4003; 0.6401 0.1714 0.3811
    0.6887 0.1922 0.3576; 0.7357 0.2159 0.3302; 0.7805 0.2433 0.2995
    0.8224 0.2752 0.2661; 0.8605 0.3119 0.2306; 0.8943 0.3534 0.1936
    0.9232 0.3994 0.1552; 0.9470 0.4492 0.1153; 0.9654 0.5022 0.0739
    0.9784 0.5579 0.0349; 0.9860 0.6158 0.0256; 0.9879 0.6753 0.0653
    0.9841 0.7361 0.1295; 0.9746 0.7977 0.2063; 0.9606 0.8591 0.2980
    0.9476 0.9174 0.4107; 0.9545 0.9659 0.5404; 0.9884 0.9984 0.6449];
map = interp1(linspace(0, 1, size(anchors, 1)), anchors, linspace(0, 1, 256));
end

% =========================================================================
%  Serial / frame
% =========================================================================

% เลือก serial port : ถ้าผู้ใช้ระบุมาก็ใช้ตามนั้น ไม่อย่างนั้นหา port ของบอร์ดให้
function port = pickPort(port)
if ~isempty(port)
    port = char(port);
    return;
end
ports = cellstr(serialportlist('available'));
if isempty(ports)
    error('No serial port found. Plug in the board, or close Arduino Serial Monitor.');
end
% Linux มี /dev/ttyS* ติดมาด้วยเสมอ ให้สนใจเฉพาะ USB serial
isUsb = ~cellfun('isempty', regexp(ports, 'ttyUSB|ttyACM|usbserial|usbmodem|^COM\d+$', 'once'));
cand = ports(isUsb);
if numel(cand) == 1
    port = cand{1};
    fprintf('Using serial port %s\n', port);
else
    fprintf('Available serial ports:\n');
    fprintf('   %s\n', ports{:});
    error('Cannot pick a port automatically. Set cfg.port, e.g. realtime_audio_scope(''port'', ''%s'').', ports{end});
end
end

% แยก frame ที่สมบูรณ์ออกจาก byte stream
%   frame = sync(4) seq(4) fs(4) n(2) missed(2) format(1) bits(1) reserved(2) samples(2n) checksum(2)
%   คืน byte ที่ยังไม่ครบ frame กลับไปใน rx เพื่อรอต่อกับข้อมูลรอบถัดไป
function [frames, rx, nBad] = parseFrames(rx)
SYNC    = uint8([165 90 195 60]);       % A5 5A C3 3C
HDR_LEN = 20;
frames = struct('seq', {}, 'fs', {}, 'n', {}, 'missed', {}, 'bits', {}, 'isSigned', {}, 'x', {});
nBad = 0;

while true
    k = strfind(char(rx), char(SYNC));
    if isempty(k)
        if numel(rx) > 3                % เก็บ 3 byte ท้ายไว้ เผื่อเป็น sync word ที่มาไม่ครบ
            rx = rx(end - 2:end);
        end
        return;
    end
    rx = rx(k(1):end);
    if numel(rx) < HDR_LEN
        return;
    end

    seq    = double(typecast(rx(5:8),   'uint32'));
    fs     = double(typecast(rx(9:12),  'uint32'));
    n      = double(typecast(rx(13:14), 'uint16'));
    missed = double(typecast(rx(15:16), 'uint16'));
    fmt    = double(rx(17));
    bits   = double(rx(18));

    if n < 2 || n > 32768 || fs < 1 || fs > 1e6 || fmt > 1 || bits < 1 || bits > 16
        rx = rx(2:end);                 % sync word ปลอม (บังเอิญตรง) -> ข้ามไปหาตัวถัดไป
        nBad = nBad + 1;
        continue;
    end

    total = HDR_LEN + 2 * n + 2;
    if numel(rx) < total
        return;                         % frame ยังมาไม่ครบ รอรอบหน้า
    end

    raw = typecast(rx(HDR_LEN + 1:HDR_LEN + 2 * n), 'uint16');
    chk = double(typecast(rx(total - 1:total), 'uint16'));
    if mod(sum(double(raw)), 65536) ~= chk
        rx = rx(2:end);
        nBad = nBad + 1;
        continue;
    end

    if fmt == 1
        x = double(typecast(raw, 'int16'));
    else
        x = double(raw);
    end

    fr.seq = seq; fr.fs = fs; fr.n = n; fr.missed = missed;
    fr.bits = bits; fr.isSigned = (fmt == 1); fr.x = x(:);
    frames(end + 1) = fr; %#ok<AGROW>
    rx = rx(total + 1:end);
end
end

% สร้าง frame จาก sample (ใช้ในโหมด demo)  รูปแบบเดียวกับที่ ESP32 ส่ง
function bytes = buildFrame(seq, fs, x, missed, fmt, bits)
if fmt == 1
    raw = typecast(int16(x(:).'), 'uint16');
else
    raw = uint16(x(:).');
end
chk = uint16(mod(sum(double(raw)), 65536));
bytes = [uint8([165 90 195 60]), typecast(uint32(seq), 'uint8'), typecast(uint32(fs), 'uint8'), ...
    typecast(uint16(numel(raw)), 'uint8'), typecast(uint16(missed), 'uint8'), ...
    uint8([fmt, bits, 0, 0]), typecast(raw, 'uint8'), typecast(chk, 'uint8')];
end

% สัญญาณจำลองสำหรับโหมด demo : 1000 Hz + 2500 Hz + noise บน DC offset แบบ MAX4466
function [bytes, blockTime] = demoFrame(seq)
fs = 10000; n = 1024;
t = (seq * n + (0:n - 1)) / fs;
x = 2000 + 600 * sin(2 * pi * 1000 * t) + 150 * sin(2 * pi * 2500 * t) + 4 * randn(1, n);
x = min(max(round(x), 0), 4095);
bytes = buildFrame(seq, fs, x, 0, 0, 12);
blockTime = n / fs;
end

% =========================================================================
%  DSP
% =========================================================================

% Window function ยาว n จุด (แบบ periodic ซึ่งเหมาะกับการทำ FFT)
function w = makeWindow(name, n)
k = (0:n - 1).';
a = 2 * pi * k / n;
switch lower(name)
    case 'hann'
        w = 0.5 - 0.5 * cos(a);
    case 'hamming'
        w = 0.54 - 0.46 * cos(a);
    case 'blackman'
        w = 0.42 - 0.5 * cos(a) + 0.08 * cos(2 * a);
    case 'flat-top'
        w = 0.21557895 - 0.41663158 * cos(a) + 0.277263158 * cos(2 * a) ...
            - 0.083578947 * cos(3 * a) + 0.006947368 * cos(4 * a);
    otherwise                           % 'Rectangular (no window)'
        w = ones(n, 1);
end
end

% Single-sided amplitude spectrum หน่วยเดียวกับ sample (ADC count, ค่า peak)
%   - ลบค่าเฉลี่ย (DC offset ของไมค์) ออกก่อน
%   - หารด้วย sum(w) เพื่อชดเชย gain ของ window : sine ที่ตรง bin พอดีจะอ่าน amplitude ได้เท่ากันทุก window
function [f, amp] = spectrumAmp(x, fs, w)
n = numel(x);
X = fft((x(:) - mean(x)) .* w(:));
nHalf = floor(n / 2) + 1;
amp = abs(X(1:nHalf)) / sum(w);
if mod(n, 2) == 0
    amp(2:end - 1) = 2 * amp(2:end - 1);    % bin ที่ Nyquist ไม่มีคู่ จึงไม่คูณ 2
else
    amp(2:end) = 2 * amp(2:end);
end
f = (0:nHalf - 1).' * fs / n;
end

% amplitude (count) -> dBFS   (0 dBFS = sine ที่ amplitude เท่ากับครึ่งช่วง ADC)
function dB = toDbfs(amp, bits)
dB = 20 * log10(max(amp / 2 ^ (bits - 1), 1e-12));
end

% หายอด (local maximum) ที่เด่นที่สุดไม่เกิน nMax ยอด
%   minSep : ระยะห่างขั้นต่ำระหว่างยอด (จำนวน bin)
%   relDb  : รับเฉพาะยอดที่ต่ำกว่ายอดสูงสุดไม่เกินเท่านี้
%   absDb  : รับเฉพาะยอดที่สูงกว่าระดับนี้ (กันไม่ให้ติดป้ายที่ noise ตอนเงียบ)
function idx = topPeaks(magDb, nMax, minSep, relDb, absDb)
m = magDb(:);
n = numel(m);
idx = zeros(1, 0);
if n < 5, return; end
isPk = false(n, 1);
isPk(2:n - 1) = m(2:n - 1) > m(1:n - 2) & m(2:n - 1) >= m(3:n);
isPk(1:2) = false;                      % ไม่นับ bin ที่ติด DC
cand = find(isPk & m >= max(m(3:end)) - relDb & m >= absDb);
[~, order] = sort(m(cand), 'descend');
cand = cand(order);
for c = cand(:).'
    if isempty(idx) || all(abs(idx - c) >= minSep)
        idx(end + 1) = c; %#ok<AGROW>
        if numel(idx) >= nMax, break; end
    end
end
end
