function task3_host(varargin)
%TASK3_HOST  Task 3 host program (MATLAB) -- same features as task3_host.py
%
%   Receives audio blocks  FPGA -> ESP32-S3 -> USB serial  and shows, in real
%   time: waveform, FFT spectrum (Hann/Rect, dB/linear), scrolling spectrogram,
%   link statistics (lost blocks, FPGA/ESP32 drops, checksum errors) and the
%   sample rate measured from the data. Includes Pause/Resume and an event
%   trigger that captures sudden changes (clap, tone on/off, frequency change).
%
%   Needs MATLAB R2019b or newer (serialport). No toolboxes required.
%   Also runs in GNU Octave 7+ for 'demo' / 'check' / 'selftest'
%   (serial needs:  pkg install -forge instrument-control; pkg load instrument-control).
%
%   USAGE (in the Command Window, from the host folder)
%     task3_host                    auto-detect the ESP32 port, open the plots
%     task3_host('COM7')            Windows port      ('/dev/ttyUSB0' or '/dev/ttyACM0' on Linux)
%     task3_host('demo')            synthetic data, no hardware needed
%     task3_host('check', 20)       no plots: 20 s Fs / lost-block report
%     task3_host('COM7', 'check', 300)
%     task3_host('demo', 15)        plots for 15 s, then saves a PNG and closes
%     task3_host('selftest')        tests the frame parser and the trigger, no hardware
%
%   BUTTONS (bottom of the window; keyboard shortcut in brackets)
%     Pause/Resume [p]   Trigger OFF/NORMAL/SINGLE [g]   Re-arm [r]
%     Detect level/spectrum [d]   Edge rise/fall/both [e]   Window Hann/Rect [w]
%     dB/Linear [l]   Save [s] -> PNG + .mat + .wav   Test ramp [t]   Normal [n]
%     Threshold slider [dB].  Close the window to stop.
%
%   FRAME FORMAT from the ESP32 (little endian, 20-byte header):
%     AA 55 33 CC | seq u16 | n u16 | flags u8 | fpga_drops u8 | spi_errs u16 |
%     esp_drops u16 | t_us u32 | fs u16 | n x u16 samples | checksum u16
%     flags: bit0 valid, bit1 test ramp, bits3..2 source (0 MCP320x, 1 MAX10, 2 tone)
%
%   EVENT TRIGGER: the stream is cut into 16 ms frames and compared with a
%   slowly-adapting background (~0.5 s).  level = 20*log10(rms/rms_bg);
%   spectrum = power-weighted mean |dB change| per FFT bin.  It fires above the
%   threshold and re-arms only after the score drops below threshold-6 dB, so
%   one event = one trigger.  The capture shows -64..+192 ms around the event
%   and the spectrum BEFORE (grey) vs AFTER (blue) the trigger.

% =============================== SETTINGS ====================================
cfg.BAUD          = 921600;   % must match SERIAL_BAUD in the ESP32 sketch
cfg.N             = 1024;     % samples per block
cfg.FS            = 16000;    % nominal sample rate
cfg.VFS           = [3.3 5.0 3.3 3.3];  % full-scale volts for source id 0..3
cfg.SRC_NAME      = {'MCP320x ADC', 'MAX10 ADC', 'FPGA test tone', '?'};
cfg.SPEC_SECONDS  = 4.0;      % spectrogram history
cfg.SPEC_NFFT     = 512;
cfg.SPEC_HOP      = 256;
cfg.RECORD_SEC    = 10.0;     % saved by 'Save' when no event is captured
cfg.RING_SEC      = 12.0;
cfg.REFRESH_S     = 0.05;     % screen refresh period
% event trigger
cfg.TRIG_FRAME    = 256;      % 16 ms analysis frame
cfg.TRIG_DB       = 12.0;     % default threshold [dB]
cfg.TRIG_ALPHA    = 0.03;     % background follows upwards slowly (~0.5 s)
cfg.TRIG_FAST     = 0.20;     % ... and fast downwards / after an event
cfg.TRIG_HYST_DB  = 6.0;
cfg.TRIG_MIN_RMS  = 0.004;    % ignore changes quieter than this [V rms]
cfg.TRIG_HOLDOFF  = 0.30;     % s between triggers
cfg.TRIG_WARMUP   = 20;       % frames
cfg.CAP_PRE       = 1024;     % samples before the trigger (64 ms)
cfg.CAP_POST      = 3072;     % samples after the trigger (192 ms)
% =============================================================================

[port, mode, secs, secsGiven] = parse_args(varargin{:});

if strcmp(mode, 'selftest')
    selftest(cfg);
    return;
end

if strcmp(port, 'demo')
    src = demo_open(cfg);
else
    src = serial_open(port, cfg.BAUD);
end
cleanupObj = onCleanup(@() source_close(src)); %#ok<NASGU>

if strcmp(mode, 'check')
    run_check(src, cfg, secs);
else
    if ~secsGiven, secs = Inf; end
    run_gui(src, cfg, secs);
end
end

% =============================================================================
%                                   ARGUMENTS
% =============================================================================
function [port, mode, secs, secsGiven] = parse_args(varargin)
port = '';  mode = 'gui';  secs = 10;  secsGiven = false;
k = 1;
while k <= numel(varargin)
    a = varargin{k};
    if isnumeric(a)
        secs = a;  secsGiven = true;
    else
        a = char(a);
        switch lower(a)
            case 'demo',     port = 'demo';
            case 'check',    mode = 'check';
                if k < numel(varargin) && isnumeric(varargin{k+1})
                    secs = varargin{k+1};  secsGiven = true;  k = k + 1;
                end
            case 'selftest', mode = 'selftest';
            otherwise,       port = a;
        end
    end
    k = k + 1;
end
end

% =============================================================================
%                                   SOURCES
% =============================================================================
function src = serial_open(port, baud)
src.kind = 'serial';
if exist('OCTAVE_VERSION', 'builtin')
    pkg('load', 'instrument-control');
end
if isempty(port)
    p = serialportlist('available');
    if isempty(p)
        error('task3_host:noport', 'No serial port found. Use task3_host(''COM7'') or task3_host(''demo'').');
    end
    port = char(p(end));
end
src.port = port;
src.s = serialport(port, baud, 'Timeout', 1);
flush(src.s);
write(src.s, uint8('n'), 'uint8');
fprintf('Opened %s @ %d baud\n', port, baud);
end

function src = demo_open(cfg)
src.kind = 'demo';
src.t0 = tic;
src.sent = 0;
src.seq = 0;
src.test = false;
src.rng = 1;
src.cfg = cfg;
fprintf('DEMO mode: synthetic 16 kS/s stream (claps every 3 s, tone change every 6 s)\n');
end

function [bytes, src] = source_read(src)
switch src.kind
    case 'serial'
        nb = src.s.NumBytesAvailable;
        if nb > 0
            bytes = uint8(read(src.s, nb, 'uint8'));
            bytes = bytes(:).';
        else
            bytes = uint8([]);
            pause(0.005);
        end
    case 'demo'
        cfg = src.cfg;  N = cfg.N;  FS = cfg.FS;
        due = floor(toc(src.t0) * FS / N);
        bytes = uint8([]);
        while src.sent < due
            k = (src.sent * N) + (0:N-1);
            if src.test
                x = 0:N-1;  flags = 3 + 2*4;
            else
                t = k / FS;
                f1 = 1000 + 500 * (mod(t, 6) >= 4 & mod(t, 6) < 5);
                ph = 2*pi*f1.*t;
                fch = 300 + 200 * mod(t, 5).^1.5;
                tc = mod(t, 3) - 1.5;
                clap = (tc >= 0 & tc < 0.08) .* 1400 .* exp(-max(tc, 0) / 0.012);
                x = 2048 + 150*sin(ph) + 50*sin(2*pi*2500*t) + 40*sin(2*pi*fch.*t) ...
                    + clap .* randn(1, N) + 15*randn(1, N);
                x = min(max(round(x), 0), 4095);
                flags = 1 + 2*4;
            end
            bytes = [bytes, build_frame(src.seq, x, flags, round(src.sent*N/FS*1e6), FS)]; %#ok<AGROW>
            src.seq = mod(src.seq + 1, 65536);
            src.sent = src.sent + 1;
        end
        if isempty(bytes), pause(0.01); end
end
end

function src_write(src, ch)
if strcmp(src.kind, 'serial')
    write(src.s, uint8(ch), 'uint8');
end
end

function source_close(src)
if strcmp(src.kind, 'serial') && isfield(src, 's')
    try
        delete(src.s);
    catch
    end
end
end

% =============================================================================
%                                FRAME PARSER
% =============================================================================
function f = build_frame(seq, x, flags, t_us, fs)
% Same layout as the ESP32 sketch (used by demo mode and the self-test).
x = uint16(x(:).');
n = numel(x);
chk = uint16(mod(sum(double(x)), 65536));
hdr = [uint8([170 85 51 204]), typecast(uint16(seq), 'uint8'), typecast(uint16(n), 'uint8'), ...
       uint8(flags), uint8(0), uint8([0 0 0 0]), typecast(uint32(t_us), 'uint8'), ...
       typecast(uint16(fs), 'uint8')];
f = [hdr, typecast(x, 'uint8'), typecast(chk, 'uint8')];
end

function [blocks, buf, bad] = parse_frames(buf, bad)
% Byte stream -> struct array of blocks. Resynchronises on AA 55 33 CC and
% drops frames whose checksum is wrong.
blocks = struct('seq', {}, 'n', {}, 'flags', {}, 'fdrop', {}, 'spiErr', {}, ...
                'espDrop', {}, 'tus', {}, 'fs', {}, 'x', {});
SYNC = char([170 85 51 204]);
HDR = 20;
while true
    k = strfind(char(buf), SYNC);
    if isempty(k)
        if numel(buf) > 3, buf = buf(end-2:end); end
        return;
    end
    buf = buf(k(1):end);
    if numel(buf) < HDR, return; end
    n = double(typecast(buf(7:8), 'uint16'));
    if n == 0 || n > 8192
        buf = buf(5:end);  bad = bad + 1;  continue;
    end
    total = HDR + 2*n + 2;
    if numel(buf) < total, return; end
    x = double(typecast(buf(HDR+1:HDR+2*n), 'uint16'));
    chk = double(typecast(buf(HDR+2*n+1:HDR+2*n+2), 'uint16'));
    if mod(sum(x), 65536) ~= chk
        buf = buf(5:end);  bad = bad + 1;  continue;
    end
    b.seq     = double(typecast(buf(5:6), 'uint16'));
    b.n       = n;
    b.flags   = double(buf(9));
    b.fdrop   = double(buf(10));
    b.spiErr  = double(typecast(buf(11:12), 'uint16'));
    b.espDrop = double(typecast(buf(13:14), 'uint16'));
    b.tus     = double(typecast(buf(15:18), 'uint32'));
    b.fs      = double(typecast(buf(19:20), 'uint16'));
    b.x       = x;
    blocks(end+1) = b; %#ok<AGROW>
    buf = buf(total+1:end);
end
end

function tf = blk_is_test(b)
tf = bitand(b.flags, 2) > 0;
end

function s = blk_source(b)
s = bitand(bitshift(b.flags, -2), 3);
end

% =============================================================================
%                                 STATISTICS
% =============================================================================
function st = stats_new()
st = struct('blocks', 0, 'gaps', 0, 'lost', 0, 'fsEst', NaN, 'testOk', NaN, ...
            'lastSeq', -1, 'seqAcc', 0, 'first', [], 'tWrap', 0, 'lastT', -1);
end

function st = stats_update(st, b)
st.blocks = st.blocks + 1;
isTest = blk_is_test(b);
if st.lastSeq >= 0
    d = mod(b.seq - st.lastSeq, 65536);
    if d ~= 1 && ~isTest
        st.gaps = st.gaps + 1;
        if d > 1, st.lost = st.lost + d - 1; end
    end
    st.seqAcc = st.seqAcc + d;
end
st.lastSeq = b.seq;
if st.lastT >= 0 && b.tus < st.lastT
    st.tWrap = st.tWrap + 2^32;          % ESP32 micros() wraps after 71 min
end
st.lastT = b.tus;
t = b.tus + st.tWrap;
if isempty(st.first) || isTest
    st.first = [st.seqAcc, t];
else
    dseq = st.seqAcc - st.first(1);
    dt = (t - st.first(2)) * 1e-6;
    if dseq >= 4 && dt > 0
        % FPGA sequence numbers count every block produced, so dropped
        % blocks do not bias the estimate.
        st.fsEst = dseq * b.n / dt;
    end
end
if isTest
    st.testOk = isequal(b.x, 0:b.n-1);
end
end

% =============================================================================
%                                 RING BUFFER
% =============================================================================
function r = ring_new(n)
r.buf = zeros(1, n);  r.size = n;  r.total = 0;
end

function r = ring_append(r, x)
n = numel(x);
idx = mod(r.total + (0:n-1), r.size) + 1;
r.buf(idx) = x;
r.total = r.total + n;
end

function y = ring_get(r, a, b)
% samples with absolute index a .. b-1 (0-based), [] if not available
if a < 0 || a < r.total - r.size || b > r.total
    y = [];  return;
end
y = r.buf(mod(a:b-1, r.size) + 1);
end

% =============================================================================
%                                EVENT TRIGGER
% =============================================================================
function tr = trig_new(cfg)
tr.mode = 'OFF';  tr.kind = 'level';  tr.edge = 'rise';  tr.thr = cfg.TRIG_DB;
tr.armed = true;  tr.armedAt = 0;  tr.count = 0;  tr.captureId = 0;
tr.capture = [];  tr.events = [];  tr.score = 0;
tr.pending = [];  tr.pos = 0;  tr.dc = NaN;  tr.bg = NaN;  tr.bgSpec = [];
tr.nframes = 0;  tr.lastTrig = -1e12;  tr.waiting = [];  tr.latched = false;
F = cfg.TRIG_FRAME;
tr.win = 0.5 - 0.5*cos(2*pi*(0:F-1)/(F-1));
end

function tr = trig_reset_stream(tr)
tr.pending = [];  tr.dc = NaN;  tr.bg = NaN;  tr.bgSpec = [];
tr.nframes = 0;  tr.waiting = [];  tr.latched = false;
end

function tr = trig_process(tr, v, startIdx, ring, cfg)
F = cfg.TRIG_FRAME;
if isempty(tr.pending), tr.pos = startIdx; end
tr.pending = [tr.pending, v];
while numel(tr.pending) >= F
    tr = trig_frame(tr, tr.pending(1:F), tr.pos, cfg);
    tr.pending = tr.pending(F+1:end);
    tr.pos = tr.pos + F;
end
if ~isempty(tr.waiting) && ring.total >= tr.waiting(1) + cfg.CAP_POST
    tr = trig_finish(tr, ring, cfg);
end
end

function tr = trig_frame(tr, f, idx, cfg)
F = cfg.TRIG_FRAME;
m = mean(f);
if isnan(tr.dc), tr.dc = m; else, tr.dc = 0.95*tr.dc + 0.05*m; end
x = f - tr.dc;
r = sqrt(mean(x.^2));
X = fft(x .* tr.win);
P = abs(X(1:F/2+1)).^2 + 1e-14;
Pdb = 10*log10(P);
if isnan(tr.bg)
    tr.bg = r;  tr.bgSpec = Pdb;
end
tr.nframes = tr.nframes + 1;
bg = tr.bg;
lvl = 20*log10((r + 1e-9) / (bg + 1e-9));
if strcmp(tr.kind, 'level')
    switch tr.edge
        case 'rise', score = lvl;       loud = r > cfg.TRIG_MIN_RMS;
        case 'fall', score = -lvl;      loud = bg > cfg.TRIG_MIN_RMS;
        otherwise,   score = abs(lvl);  loud = max(r, bg) > cfg.TRIG_MIN_RMS;
    end
else
    w = max(P, 10.^(tr.bgSpec/10));
    score = sum(w .* abs(Pdb - tr.bgSpec)) / sum(w);
    loud = max(r, bg) > cfg.TRIG_MIN_RMS;
end
tr.score = score;
if tr.latched && score < max(tr.thr - cfg.TRIG_HYST_DB, 0.5*tr.thr)
    tr.latched = false;
end
fire = ~strcmp(tr.mode, 'OFF') && tr.armed && isempty(tr.waiting) && ~tr.latched ...
       && tr.nframes > cfg.TRIG_WARMUP && loud && score > tr.thr ...
       && (idx - tr.lastTrig) > cfg.TRIG_HOLDOFF * cfg.FS;
if fire
    tr.lastTrig = idx;
    tr.latched = true;
    tr.waiting = [idx, score, lvl, bg, r];
    tr.events(end+1) = idx;
    if numel(tr.events) > 100, tr.events = tr.events(end-99:end); end
    if strcmp(tr.mode, 'SINGLE'), tr.armed = false; end
end
% background: slow upwards, fast downwards; fast in both directions while
% an event is latched, so the new steady state is learnt quickly
if tr.latched
    a = cfg.TRIG_FAST;  aS = cfg.TRIG_FAST;
else
    if r > bg, a = cfg.TRIG_ALPHA; else, a = cfg.TRIG_FAST; end
    aS = cfg.TRIG_FAST * ones(size(Pdb));
    aS(Pdb > tr.bgSpec) = cfg.TRIG_ALPHA;
end
tr.bg = (1 - a)*bg + a*r;
tr.bgSpec = (1 - aS).*tr.bgSpec + aS.*Pdb;
end

function tr = trig_finish(tr, ring, cfg)
w = tr.waiting;  tr.waiting = [];
seg = ring_get(ring, w(1) - cfg.CAP_PRE, w(1) + cfg.CAP_POST);
if isempty(seg), return; end
tr.count = tr.count + 1;
tr.captureId = tr.captureId + 1;
tr.capture = struct('id', tr.captureId, 'n', tr.count, 'idx', w(1), 'score', w(2), ...
    'levelDb', w(3), 'rmsBefore', w(4), 'rmsAfter', w(5), 'kind', tr.kind, ...
    'edge', tr.edge, 'samples', seg, 'wall', datestr(now, 'HH:MM:SS'));
fprintf('[trigger #%d] %s  %s/%s  score=%5.1f dB  level change=%+5.1f dB  rms %.1f -> %.1f mV\n', ...
    tr.count, tr.capture.wall, tr.kind, tr.edge, w(2), w(3), w(4)*1e3, w(5)*1e3);
end

% =============================================================================
%                                  ANALYSIS
% =============================================================================
function [f, mag] = spectrum(v, fs, useHann)
n = numel(v);
x = v - mean(v);
if useHann
    w = 0.5 - 0.5*cos(2*pi*(0:n-1)/(n-1));
else
    w = ones(1, n);
end
X = fft(x .* w);
mag = 2*abs(X(1:floor(n/2)+1)) / sum(w);     % amplitude-corrected
f = (0:floor(n/2)) * fs / n;
end

function [fpk, apk] = peak_freq(f, mag)
[~, k] = max(mag(2:end));  k = k + 1;        % skip DC
p = 0;
if k > 1 && k < numel(mag)
    a = log(mag(k-1) + 1e-12);  b = log(mag(k) + 1e-12);  c = log(mag(k+1) + 1e-12);
    den = a - 2*b + c;
    if den ~= 0, p = 0.5*(a - c)/den; end
end
fpk = (k - 1 + p) * (f(2) - f(1));
apk = mag(k);
end

% =============================================================================
%                                  CHECK MODE
% =============================================================================
function run_check(src, cfg, secs)
fprintf('collecting for %g s ...\n', secs);
buf = uint8([]);  bad = 0;  st = stats_new();  last = [];
t0 = tic;  tPrint = 1;
while toc(t0) < secs
    [bytes, src] = source_read(src);
    buf = [buf, bytes]; %#ok<AGROW>
    [blocks, buf, bad] = parse_frames(buf, bad);
    for i = 1:numel(blocks)
        st = stats_update(st, blocks(i));
        last = blocks(i);
    end
    if toc(t0) >= tPrint
        tPrint = tPrint + 1;
        if isempty(last)
            fprintf('  no frames yet\n');
        else
            fprintf(['  blocks=%5d  seq=%5d  Fs_est=%9.2f S/s  gaps=%d lost=%d  fpga_drop=%d  ' ...
                     'spi_err=%d esp_drop=%d bad_usb=%d  src=%s\n'], st.blocks, last.seq, st.fsEst, ...
                     st.gaps, st.lost, last.fdrop, last.spiErr, last.espDrop, bad, ...
                     cfg.SRC_NAME{blk_source(last)+1});
        end
    end
end
ok = abs(st.fsEst - cfg.FS) < 0.002*cfg.FS;
if ok, verdict = 'OK'; else, verdict = 'CHECK'; end
fprintf('\nRESULT: Fs_est = %.2f S/s (nominal %d)  -> %s;  lost blocks = %d\n', ...
        st.fsEst, cfg.FS, verdict, st.lost);
end

% =============================================================================
%                                   GUI MODE
% =============================================================================
function run_gui(src, cfg, runSecs)
N = cfg.N;  FS = cfg.FS;
nCols = round(cfg.SPEC_SECONDS * FS / cfg.SPEC_HOP);
nBins = cfg.SPEC_NFFT/2 + 1;
specImg = -100 * ones(nBins, nCols);
specTail = [];  specCount = 0;
specWin = 0.5 - 0.5*cos(2*pi*(0:cfg.SPEC_NFFT-1)/(cfg.SPEC_NFFT-1));

buf = uint8([]);  bad = 0;  st = stats_new();
ring = ring_new(round(cfg.RING_SEC * FS));
tr = trig_new(cfg);
lastBlk = [];  lastSrc = -1;  shownCap = 0;  frozenCap = 0;

% ------------------------------------------------------------------ figure
fig = figure('Name', 'Task 3 - FPGA audio sampling (MATLAB)', 'NumberTitle', 'off', ...
             'Color', 'w', 'Position', [80 60 1150 860], 'KeyPressFcn', @on_key);
ud = struct('paused', false, 'hann', true, 'db', true, 'cmd', '', 'save', false, ...
            'mode', 'OFF', 'kind', 'level', 'edge', 'rise', 'thr', cfg.TRIG_DB, 'rearm', false);
set(fig, 'UserData', ud);

info = uicontrol(fig, 'Style', 'text', 'Units', 'normalized', 'Position', [0.01 0.945 0.98 0.05], ...
                 'HorizontalAlignment', 'left', 'FontName', 'Courier', 'FontSize', 9, ...
                 'BackgroundColor', 'w', 'String', 'waiting for data ...');

axT = axes('Parent', fig, 'Position', [0.07 0.70 0.90 0.20]);
tms = (0:N-1)/FS*1e3;
hT = plot(axT, tms, zeros(1, N), 'Color', [0 0.45 0.74]);
hold(axT, 'on');
hT0 = plot(axT, [0 0], [0 5], 'r--', 'LineWidth', 1.2, 'Visible', 'off');
xlim(axT, [0 tms(end)]);  ylim(axT, [0 3.3]);  grid(axT, 'on');
xlabel(axT, 'time [ms]');  ylabel(axT, 'voltage [V]');
ttlT = title(axT, 'LIVE', 'HorizontalAlignment', 'left', 'Units', 'normalized', 'Position', [0 1.02]);

axF = axes('Parent', fig, 'Position', [0.07 0.42 0.90 0.20]);
fAx = (0:N/2)*FS/N;
hF2 = plot(axF, fAx, nan(size(fAx)), 'Color', [0.6 0.6 0.6]);
hold(axF, 'on');
hF = plot(axF, fAx, -120*ones(size(fAx)), 'Color', [0 0.45 0.74]);
hPk = plot(axF, NaN, NaN, 'rv', 'MarkerFaceColor', 'r');
xlim(axF, [0 FS/2]);  ylim(axF, [-110 10]);  grid(axF, 'on');
xlabel(axF, 'frequency [Hz]');  ylabel(axF, 'amplitude [dBV]');
hLeg = legend(axF, [hF2 hF], {'before trigger', 'after trigger'}, 'Location', 'northeast');
set(hLeg, 'Visible', 'off');

axS = axes('Parent', fig, 'Position', [0.07 0.15 0.84 0.20]);
hS = imagesc(axS, [-cfg.SPEC_SECONDS 0], [0 FS/2], specImg);
set(axS, 'YDir', 'normal');  caxis(axS, [-100 -10]);
try, colormap(axS, parula(256)); catch, colormap(axS, jet(256)); end %#ok<NOCOM>
hold(axS, 'on');
hEv = plot(axS, NaN, NaN, 'rv', 'MarkerFaceColor', 'r', 'MarkerSize', 7);
xlabel(axS, 'time [s]   (red marks = trigger events)');  ylabel(axS, 'frequency [Hz]');
cb = colorbar(axS);  ylabel(cb, 'dBV');
set(axS, 'Position', [0.07 0.15 0.84 0.20]);
set(cb, 'Position', [0.925 0.15 0.015 0.20]);

% ------------------------------------------------------------------ controls
y = 0.075;  h = 0.042;
bPause = mk_btn(fig, 'Pause',          [0.01 y 0.08 h], @(~,~) toggle_ud(fig, 'paused'));
pMode  = uicontrol(fig, 'Style', 'popupmenu', 'Units', 'normalized', 'Position', [0.10 y 0.12 h], ...
                   'String', {'Trigger: OFF', 'Trigger: NORMAL', 'Trigger: SINGLE'}, ...
                   'Callback', @(hh,~) set_ud(fig, 'mode', pick({'OFF','NORMAL','SINGLE'}, get(hh,'Value'))));
mk_btn(fig, 'Re-arm',                  [0.23 y 0.07 h], @(~,~) set_ud(fig, 'rearm', true));
pKind  = uicontrol(fig, 'Style', 'popupmenu', 'Units', 'normalized', 'Position', [0.31 y 0.12 h], ...
                   'String', {'Detect: level', 'Detect: spectrum'}, ...
                   'Callback', @(hh,~) set_ud(fig, 'kind', pick({'level','spectrum'}, get(hh,'Value'))));
pEdge  = uicontrol(fig, 'Style', 'popupmenu', 'Units', 'normalized', 'Position', [0.44 y 0.10 h], ...
                   'String', {'Edge: rise', 'Edge: fall', 'Edge: both'}, ...
                   'Callback', @(hh,~) set_ud(fig, 'edge', pick({'rise','fall','both'}, get(hh,'Value'))));
bWin   = mk_btn(fig, 'Window: Hann',   [0.55 y 0.10 h], @(~,~) toggle_ud(fig, 'hann'));
bDb    = mk_btn(fig, 'Scale: dB',      [0.66 y 0.08 h], @(~,~) toggle_ud(fig, 'db'));
mk_btn(fig, 'Save',                    [0.75 y 0.06 h], @(~,~) set_ud(fig, 'save', true));
mk_btn(fig, 'Test ramp',               [0.82 y 0.08 h], @(~,~) set_ud(fig, 'cmd', 't'));
mk_btn(fig, 'Normal',                  [0.91 y 0.08 h], @(~,~) set_ud(fig, 'cmd', 'n'));
uicontrol(fig, 'Style', 'text', 'Units', 'normalized', 'Position', [0.01 0.02 0.11 0.03], ...
          'String', 'Threshold [dB]', 'BackgroundColor', 'w', 'HorizontalAlignment', 'right');
sThr = uicontrol(fig, 'Style', 'slider', 'Units', 'normalized', 'Position', [0.13 0.022 0.40 0.03], ...
                 'Min', 3, 'Max', 40, 'Value', cfg.TRIG_DB, 'SliderStep', [0.5 2]/37, ...
                 'Callback', @(hh,~) set_ud(fig, 'thr', round(get(hh,'Value')*2)/2));
tScore = uicontrol(fig, 'Style', 'text', 'Units', 'normalized', 'Position', [0.55 0.02 0.44 0.03], ...
                   'HorizontalAlignment', 'left', 'FontName', 'Courier', 'BackgroundColor', 'w', 'String', '');

% ------------------------------------------------------------------ loop
tDraw = tic;  tRun = tic;
while ishandle(fig)
    if toc(tRun) > runSecs                       % task3_host(..., seconds)
        draw_now(true);
        ud = get(fig, 'UserData');
        cap = [];
        if ~strcmp(tr.mode, 'OFF') && shownCap > 0, cap = tr.capture; end
        save_recording(fig, ring, cap, cfg, cfg.VFS(max(lastSrc,0)+1));
        close(fig);
        break;
    end
    ud = get(fig, 'UserData');
    % --- apply UI state to the trigger
    tr.mode = ud.mode;  tr.kind = ud.kind;  tr.edge = ud.edge;  tr.thr = ud.thr;
    if ud.rearm
        tr.armed = true;  tr.armedAt = tr.captureId;  ud.rearm = false;  ud.paused = false;
    end
    if ~isempty(ud.cmd)
        src_write(src, ud.cmd);
        if strcmp(src.kind, 'demo'), src.test = strcmp(ud.cmd, 't'); end
        ud.cmd = '';
    end
    if ud.save
        ud.save = false;
        cap = [];
        if ~strcmp(tr.mode, 'OFF') && shownCap > 0, cap = tr.capture; end
        vfs = 3.3;  if ~isempty(lastBlk), vfs = cfg.VFS(blk_source(lastBlk)+1); end
        save_recording(fig, ring, cap, cfg, vfs);
    end
    set(fig, 'UserData', ud);

    % --- receive + process every block (also while paused)
    [bytes, src] = source_read(src);
    buf = [buf, bytes]; %#ok<AGROW>
    [blocks, buf, bad] = parse_frames(buf, bad);
    for i = 1:numel(blocks)
        b = blocks(i);
        st = stats_update(st, b);
        lastBlk = b;
        if blk_is_test(b)
            tr = trig_reset_stream(tr);
            continue;
        end
        s = blk_source(b);
        if s ~= lastSrc, tr = trig_reset_stream(tr); lastSrc = s; end
        v = b.x * cfg.VFS(s+1) / 4096;
        startIdx = ring.total;
        ring = ring_append(ring, v);
        tr = trig_process(tr, v, startIdx, ring, cfg);
        % spectrogram (STFT over the continuous stream)
        specCount = specCount + b.n;
        specTail = [specTail, v]; %#ok<AGROW>
        cols = [];
        while numel(specTail) >= cfg.SPEC_NFFT
            seg = specTail(1:cfg.SPEC_NFFT);
            seg = (seg - mean(seg)) .* specWin;
            m = 2*abs(fft(seg)) / sum(specWin);
            cols(:, end+1) = 20*log10(m(1:nBins).' + 1e-9); %#ok<AGROW>
            specTail = specTail(cfg.SPEC_HOP+1:end);
        end
        if ~isempty(cols)
            specImg = [specImg(:, size(cols,2)+1:end), cols];
        end
    end

    % --- SINGLE: freeze the whole display on a new capture
    if strcmp(tr.mode, 'SINGLE') && ~tr.armed && ~isempty(tr.capture) ...
            && tr.capture.id > tr.armedAt && tr.capture.id ~= frozenCap
        frozenCap = tr.capture.id;
        draw_now(true);
        ud = get(fig, 'UserData');  ud.paused = true;  set(fig, 'UserData', ud);
    end

    if ~ishandle(fig), break; end
    if toc(tDraw) >= cfg.REFRESH_S
        tDraw = tic;
        draw_now(false);
    end
end

    % nested drawing routine (shares the variables of run_gui)
    function draw_now(force)
        if ~ishandle(fig) || isempty(lastBlk), return; end
        u = get(fig, 'UserData');
        set(bPause, 'String', ternary(u.paused, 'Resume', 'Pause'), ...
            'BackgroundColor', ternary(u.paused, [0.96 0.71 0.71], [0.94 0.94 0.94]));
        set(bWin, 'String', ternary(u.hann, 'Window: Hann', 'Window: Rect'));
        set(bDb, 'String', ternary(u.db, 'Scale: dB', 'Scale: Linear'));
        set(pMode, 'Value', find(strcmp({'OFF','NORMAL','SINGLE'}, tr.mode)));
        set(pKind, 'Value', find(strcmp({'level','spectrum'}, tr.kind)));
        set(pEdge, 'Value', find(strcmp({'rise','fall','both'}, tr.edge)));
        set(sThr, 'Value', tr.thr);
        armedTxt = '';
        if ~strcmp(tr.mode, 'OFF')
            armedTxt = ternary(tr.armed, 'ARMED', 'done (Re-arm)');
        end
        set(tScore, 'String', sprintf('score %5.1f dB  thr %.1f  %s  events=%d', ...
            tr.score, tr.thr, armedTxt, tr.count));
        if u.paused && ~force, drawnow_safe(); return; end

        sid = blk_source(lastBlk);
        vfs = cfg.VFS(sid+1);
        set(hS, 'CData', specImg);
        ev = -(specCount - tr.events) / FS;
        ev = ev(ev >= -cfg.SPEC_SECONDS);
        set(hEv, 'XData', ev, 'YData', 0.95*FS/2*ones(size(ev)));

        cap = tr.capture;
        if strcmp(tr.mode, 'SINGLE') && ~isempty(cap) && cap.id <= tr.armedAt
            cap = [];                                % waiting for a NEW single shot
        end
        if ~strcmp(tr.mode, 'OFF') && ~isempty(cap)
            shownCap = cap.id;
            v = cap.samples;
            tt = ((0:numel(v)-1) - cfg.CAP_PRE) / FS * 1e3;
            set(hT, 'XData', tt, 'YData', v);
            xlim(axT, [tt(1) tt(end)]);  xlabel(axT, 'time relative to trigger [ms]');
            set(hT0, 'Visible', 'on', 'YData', [0 vfs]);
            before = v(cfg.CAP_PRE-N+1:cfg.CAP_PRE);
            after  = v(cfg.CAP_PRE+1:cfg.CAP_PRE+N);
            [~, m0] = spectrum(before, FS, u.hann);
            [f, m1] = spectrum(after,  FS, u.hann);
            set(hF2, 'YData', scale_mag(m0, u.db));
            set(hF,  'YData', scale_mag(m1, u.db));
            set(hLeg, 'Visible', 'on');
            [fpk, apk] = peak_freq(f, m1);
            set(ttlT, 'Color', [0.8 0.1 0.1], 'String', sprintf( ...
                'CAPTURED EVENT #%d (%s)  %s/%s  score=%.1f dB  level %+.1f dB  rms %.1f -> %.1f mV  peak after = %.1f Hz', ...
                cap.n, cap.wall, cap.kind, cap.edge, cap.score, cap.levelDb, cap.rmsBefore*1e3, cap.rmsAfter*1e3, fpk));
        else
            shownCap = 0;
            v = lastBlk.x * vfs / 4096;
            set(hT, 'XData', tms, 'YData', v);
            xlim(axT, [0 tms(end)]);  xlabel(axT, 'time [ms]');
            set(hT0, 'Visible', 'off');
            set(hF2, 'YData', nan(size(fAx)));  set(hLeg, 'Visible', 'off');
            [f, m1] = spectrum(v, FS, u.hann);
            set(hF, 'YData', scale_mag(m1, u.db));
            [fpk, apk] = peak_freq(f, m1);
            if strcmp(tr.mode, 'OFF')
                set(ttlT, 'Color', 'k', 'String', 'LIVE');
            else
                set(ttlT, 'Color', 'k', 'String', sprintf('LIVE - waiting for trigger (%s, %s/%s, > %.1f dB)', ...
                    tr.mode, tr.kind, tr.edge, tr.thr));
            end
        end
        ylim(axT, [0 vfs]);
        set(hPk, 'XData', fpk, 'YData', scale_mag(apk, u.db));
        if u.db
            ylim(axF, [-110 10]);  ylabel(axF, 'amplitude [dBV]');
        else
            ylim(axF, [0 max(1e-3, 1.2*max(m1(2:end)))]);  ylabel(axF, 'amplitude [V]');
        end

        vl = lastBlk.x * vfs / 4096;
        clip = 100 * mean(lastBlk.x <= 4 | lastBlk.x >= 4091);
        extra = '';
        if blk_is_test(lastBlk)
            extra = ternary(st.testOk, '   TEST RAMP: OK', '   TEST RAMP: ERROR');
        end
        set(info, 'String', sprintf([ ...
            'src=%-14s seq=%5d  Fs_est=%8.1f S/s  df=Fs/N=%.3f Hz  window=%s  peak=%.1f Hz%s\n' ...
            'Vpp=%.3f V  DC=%.3f V  clip=%4.1f%%  lost=%d  fpga_drop=%d  spi_err=%d  esp_drop=%d  bad_usb=%d'], ...
            cfg.SRC_NAME{sid+1}, lastBlk.seq, st.fsEst, FS/N, ternary(u.hann, 'Hann', 'Rect'), fpk, extra, ...
            max(vl) - min(vl), mean(vl), clip, st.lost, lastBlk.fdrop, lastBlk.spiErr, lastBlk.espDrop, bad));
        drawnow_safe();
    end

    function on_key(~, ev)
        switch ev.Character
            case 'p', toggle_ud(fig, 'paused');
            case 'w', toggle_ud(fig, 'hann');
            case 'l', toggle_ud(fig, 'db');
            case 's', set_ud(fig, 'save', true);
            case 't', set_ud(fig, 'cmd', 't');
            case 'n', set_ud(fig, 'cmd', 'n');
            case 'r', set_ud(fig, 'rearm', true);
            case 'g', cycle_ud(fig, 'mode', {'OFF','NORMAL','SINGLE'});  set_ud(fig, 'rearm', true);
            case 'd', cycle_ud(fig, 'kind', {'level','spectrum'});
            case 'e', cycle_ud(fig, 'edge', {'rise','fall','both'});
        end
    end
end

% ------------------------------------------------------------------ GUI helpers
function b = mk_btn(fig, label, pos, cb)
b = uicontrol(fig, 'Style', 'pushbutton', 'Units', 'normalized', 'Position', pos, ...
              'String', label, 'Callback', cb);
end

function set_ud(fig, field, value)
u = get(fig, 'UserData');  u.(field) = value;  set(fig, 'UserData', u);
end

function toggle_ud(fig, field)
u = get(fig, 'UserData');  u.(field) = ~u.(field);  set(fig, 'UserData', u);
end

function cycle_ud(fig, field, opts)
u = get(fig, 'UserData');
k = find(strcmp(opts, u.(field)));
u.(field) = opts{mod(k, numel(opts)) + 1};
set(fig, 'UserData', u);
end

function v = pick(opts, k)
v = opts{k};
end

function y = scale_mag(m, useDb)
if useDb, y = 20*log10(m + 1e-9); else, y = m; end
end

function out = ternary(c, a, b)
if c, out = a; else, out = b; end
end

function drawnow_safe()
try
    drawnow('limitrate');
catch
    drawnow;
end
end

function save_recording(fig, ring, cap, cfg, vfs)
stamp = datestr(now, 'yyyymmdd_HHMMSS');
try
    print(fig, '-dpng', '-r150', sprintf('task3_%s.png', stamp));
    fprintf('saved task3_%s.png\n', stamp);
catch err
    fprintf('PNG not saved: %s\n', err.message);
end
fs = cfg.FS; %#ok<NASGU>
if ~isempty(cap)
    volts = cap.samples; %#ok<NASGU>
    pre = cfg.CAP_PRE; %#ok<NASGU>
    info = rmfield(cap, 'samples'); %#ok<NASGU>
    base = sprintf('task3_event%d_%s', cap.n, stamp);
    save([base '.mat'], 'volts', 'fs', 'pre', 'info');
    write_wav([base '.wav'], cap.samples, vfs, cfg.FS);
    fprintf('saved %s.mat/.wav (captured event)\n', base);
    return;
end
n = min(round(cfg.RECORD_SEC * cfg.FS), min(ring.total, ring.size));
if n == 0, fprintf('nothing to save\n'); return; end
volts = ring_get(ring, ring.total - n, ring.total);
base = sprintf('task3_rec_%s', stamp);
save([base '.mat'], 'volts', 'fs');
write_wav([base '.wav'], volts, vfs, cfg.FS);
fprintf('saved %s.mat/.wav (%.1f s)\n', base, n / cfg.FS);
end

function write_wav(file, volts, vfs, fs)
code = volts / vfs * 4096;
y = (code - 2048) / 2048;            % -1..+1 around mid-scale
audiowrite(file, min(max(y(:), -1), 1), fs);
end

% =============================================================================
%                                  SELF TEST
% =============================================================================
function selftest(cfg)
fprintf('--- task3_host self-test ---\n');
ok = true;
% 1) parser: junk, good frame, corrupted frame, good frame split in pieces
f1 = build_frame(1, 0:1023, 1, 0, 16000);
f2 = build_frame(2, 100*ones(1, 1024), 1, 64000, 16000);  f2(100) = bitxor(f2(100), 255);
f3 = build_frame(3, 1023:-1:0, 1, 128000, 16000);
stream = [uint8('junk'), uint8([170 85]), f1, f2, uint8('xx'), f3];
buf = uint8([]);  bad = 0;  got = [];
for i = 1:333:numel(stream)
    buf = [buf, stream(i:min(i+332, end))]; %#ok<AGROW>
    [blocks, buf, bad] = parse_frames(buf, bad);
    got = [got, [blocks.seq]]; %#ok<AGROW>
end
fprintf('parser: frames %s, bad %d  -> ', mat2str(got), bad);
if isequal(got, [1 3]) && bad >= 1, fprintf('OK\n'); else, fprintf('FAIL\n'); ok = false; end

% 2) Fs estimate from frame timestamps
st = stats_new();
for k = 0:20
    st = stats_update(st, struct('seq', k, 'n', 1024, 'flags', 1, 'tus', round(k*64000), 'x', []));
end
fprintf('Fs estimate: %.2f S/s  -> ', st.fsEst);
if abs(st.fsEst - 16000) < 1, fprintf('OK\n'); else, fprintf('FAIL\n'); ok = false; end

% 3) spectrum peak on / between bins
for f0 = [1000, 1007.8125]
    t = (0:1023)/16000;
    [f, m] = spectrum(1 + 0.5*sin(2*pi*f0*t), 16000, true);
    fpk = peak_freq(f, m);
    fprintf('peak %.4f Hz -> %.2f Hz  -> ', f0, fpk);
    if abs(fpk - f0) < 0.5, fprintf('OK\n'); else, fprintf('FAIL\n'); ok = false; end
end

% 4) trigger: tone on at 3 s, off at 5 s in a quiet room
t = (0:8*16000-1)/16000;
randn('seed', 3); %#ok<RAND>
y = (2048 + 6*randn(size(t)) + 400*sin(2*pi*800*t).*(t >= 3 & t < 5)) * 3.3/4096;
edges = {'rise', 'fall', 'both'};  want = {3, 5, [3 5]};
for e = 1:3
    r = ring_new(200000);  tr = trig_new(cfg);  tr.mode = 'NORMAL';  tr.edge = edges{e};
    fired = [];
    for i = 1:1024:numel(y)-1024
        v = y(i:i+1023);  s0 = r.total;  r = ring_append(r, v);
        c0 = tr.captureId;
        evalc('tr = trig_process(tr, v, s0, r, cfg);');
        if tr.captureId ~= c0, fired(end+1) = tr.capture.idx/16000; end %#ok<AGROW>
    end
    fprintf('trigger level/%s: %s s  -> ', edges{e}, mat2str(round(fired*100)/100));
    if numel(fired) == numel(want{e}) && all(abs(fired - want{e}) < 0.05)
        fprintf('OK\n');
    else
        fprintf('FAIL\n'); ok = false;
    end
end
if ok, fprintf('=== SELF-TEST PASSED ===\n'); else, fprintf('=== SELF-TEST FAILED ===\n'); end
end
