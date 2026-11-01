%% Task 2 — INMP441 real-time viewer (waveform, FFT, spectrogram)
% Receives frames from inmp441_stream.ino:
%   [AA 55 AA 55][uint32 seq][uint32 drops][N x int16]
% Close the figure window to stop.

clear; clc;

%% ---------------- Settings ----------------
PORT = "/dev/ttyUSB0";        % check with serialportlist("available")
BAUD = 921600;
FS   = 16000;
N    = 1024;

NFFT_S = 256;         % spectrogram frame length (16 ms)
HOP    = 128;         % spectrogram hop (8 ms)
SPEC_SECONDS = 3;     % spectrogram history shown

%% ---------------- Derived ----------------
HDR   = 12;
FRAME = HDR + 2*N;

w   = 0.5 - 0.5*cos(2*pi*(0:N-1)'/(N-1));        % Hann window (no toolbox needed)
wS  = 0.5 - 0.5*cos(2*pi*(0:NFFT_S-1)'/(NFFT_S-1));
f   = (0:N/2)' * FS/N;                             % FFT resolution = FS/N = 15.625 Hz
fS  = (0:NFFT_S/2)' * FS/NFFT_S;
nCols   = round(SPEC_SECONDS*FS/HOP);
specImg = -120*ones(NFFT_S/2+1, nCols);
tail    = zeros(NFFT_S-HOP, 1);                    % keeps spectrogram continuous across blocks

%% ---------------- Serial ----------------
s = serialport(PORT, BAUD, "Timeout", 2);
flush(s);

%% ---------------- Figure ----------------
fig = figure('Name', 'INMP441 Real-Time', 'NumberTitle', 'off');

ax1 = subplot(3,1,1);
hT = plot(ax1, (0:N-1)/FS*1000, zeros(N,1));
xlabel(ax1, 'Time (ms)'); ylabel(ax1, 'Amplitude'); grid(ax1, 'on');
title(ax1, 'Waveform');

ax2 = subplot(3,1,2);
hF = plot(ax2, f, -120*ones(size(f)));
xlim(ax2, [0 FS/2]); ylim(ax2, [-120 0]);
xlabel(ax2, 'Frequency (Hz)'); ylabel(ax2, 'Magnitude (dBFS)'); grid(ax2, 'on');
title(ax2, 'FFT (Hann window)');

ax3 = subplot(3,1,3);
hS = imagesc(ax3, (-nCols+1:0)*HOP/FS, fS, specImg);
axis(ax3, 'xy'); caxis(ax3, [-110 -20]); colorbar(ax3);
xlabel(ax3, 'Time (s)'); ylabel(ax3, 'Frequency (Hz)');
title(ax3, 'Spectrogram');

%% ---------------- Main loop ----------------
rx = zeros(1, 0);
lastSeq = NaN; lost = 0; nBlocks = 0; t0 = tic;
x = zeros(N,1); espDrops = 0;

while ishandle(fig)
    nAvail = s.NumBytesAvailable;
    if nAvail == 0
        pause(0.005);
        continue;
    end
    rx = [rx, read(s, nAvail, "uint8")]; %#ok<AGROW>

    % If MATLAB falls behind, keep only the newest data
    if numel(rx) > 10*FRAME
        rx = rx(end-2*FRAME+1:end);
    end

    gotNew = false;
    while numel(rx) >= FRAME
        k = find(rx(1:end-3)==170 & rx(2:end-2)==85 & rx(3:end-1)==170 & rx(4:end)==85, 1);
        if isempty(k)
            rx = rx(end-2:end);            % keep possible partial header
            break;
        end
        if numel(rx) - k + 1 < FRAME
            rx = rx(k:end);                % wait for the rest of the frame
            break;
        end

        fr = uint8(rx(k:k+FRAME-1));
        rx = rx(k+FRAME:end);

        seq      = double(typecast(fr(5:8),  'uint32'));
        espDrops = double(typecast(fr(9:12), 'uint32'));
        x        = double(typecast(fr(13:end), 'int16'))';

        if ~isnan(lastSeq) && seq ~= lastSeq + 1
            lost = lost + max(seq - lastSeq - 1, 0);
        end
        lastSeq = seq;
        nBlocks = nBlocks + 1;
        gotNew  = true;

        % ---- Spectrogram columns for this block ----
        xs = x - mean(x);
        stream = [tail; xs];
        nf = floor((numel(stream) - NFFT_S)/HOP) + 1;
        idx = (1:NFFT_S)' + (0:nf-1)*HOP;
        Fr = fft(stream(idx) .* wS);
        S  = 20*log10(abs(Fr(1:NFFT_S/2+1, :))/(sum(wS)/2)/32768 + eps);
        specImg = [specImg(:, nf+1:end), S];
        tail = stream(end-(NFFT_S-HOP)+1:end);
    end

    if ~gotNew, continue; end

    % ---- Waveform ----
    xd = x - mean(x);                    % remove DC offset
    set(hT, 'YData', xd);

    % ---- FFT ----
    X  = fft(xd .* w);
    XdB = 20*log10(abs(X(1:N/2+1))/(sum(w)/2)/32768 + eps);
    set(hF, 'YData', XdB);
    [~, kmax] = max(XdB(2:end));
    title(ax2, sprintf('FFT (Hann)  —  dominant: %.1f Hz', f(kmax+1)));

    % ---- Spectrogram ----
    set(hS, 'CData', specImg);

    title(ax1, sprintf('Waveform  —  blocks: %d, rate ≈ %.0f S/s, lost: %d, ESP drops: %d', ...
        nBlocks, nBlocks*N/toc(t0), lost, espDrops));

    drawnow limitrate;
end

clear s;
disp('Stopped.');
