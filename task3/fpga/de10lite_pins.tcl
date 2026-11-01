# =============================================================================
# de10lite_pins.tcl  --  pin assignments for de10lite_audio_top (DE10-Lite)
# Sourced by create_project.tcl, or run in Quartus: Tools > Tcl Scripts.
#
# GPIO header (JP1) physical pin numbers: GPIO[0..9] = pins 1..10,
# pin 11 = 5 V, pin 12 = GND, GPIO[10] = pin 13, pin 29 = 3.3 V, pin 30 = GND.
# All GPIO are 3.3-V LVTTL -> direct connection to ESP32 (3.3 V) is safe.
# Verified against Terasic DE10-Lite User Manual, Table 3-7 (GPIO) / 3-2 (clock).
# =============================================================================

# clock / keys / switches / LEDs
set_location_assignment PIN_P11 -to MAX10_CLK1_50
set_location_assignment PIN_B8  -to KEY[0]
set_location_assignment PIN_A7  -to KEY[1]

set sw_pins  {C10 C11 D12 C12 A12 B12 A13 A14 B14 F15}
set led_pins {A8 A9 A10 B10 D13 C13 E14 D14 A11 B11}
for {set i 0} {$i < 10} {incr i} {
  set_location_assignment PIN_[lindex $sw_pins $i]  -to SW[$i]
  set_location_assignment PIN_[lindex $led_pins $i] -to LEDR[$i]
}

# GPIO header JP1                          header pin   connect to
set_location_assignment PIN_V10 -to spi_sclk   ;# 1   ESP32-S3 UNO IO12 (D13, SCK)
set_location_assignment PIN_W10 -to spi_mosi   ;# 2   ESP32-S3 UNO IO11 (D11, MOSI)
set_location_assignment PIN_V9  -to spi_miso   ;# 3   ESP32-S3 UNO IO13 (D12, MISO)
set_location_assignment PIN_W9  -to spi_cs_n   ;# 4   ESP32-S3 UNO IO10 (D10, CS)
set_location_assignment PIN_V8  -to drdy       ;# 5   ESP32-S3 UNO IO14 (D7, DRDY)
set_location_assignment PIN_W8  -to fs_tick    ;# 6   scope CH1 (8 kHz square)
set_location_assignment PIN_V7  -to adc_cs_n   ;# 7   MCP3201 pin 5 CS  (MCP3202: pin 1)
set_location_assignment PIN_W7  -to adc_sclk   ;# 8   MCP3201 pin 7 CLK (MCP3202: pin 7)
set_location_assignment PIN_W6  -to adc_din    ;# 9   MCP3202 pin 5 DIN (MCP3201: not connected)
set_location_assignment PIN_V5  -to adc_dout   ;# 10  MCP3201 pin 6 DOUT (MCP3202: pin 6)
set_location_assignment PIN_W5  -to blk_tick   ;# 13  scope CH2 (block toggle)
#                                                12/30 GND -> ESP32 GND (common!)

set io_list {MAX10_CLK1_50 KEY[*] SW[*] LEDR[*] spi_sclk spi_mosi spi_miso spi_cs_n
             drdy fs_tick blk_tick adc_cs_n adc_sclk adc_din adc_dout}
foreach p $io_list {
  set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to $p
}

# keep CS de-asserted and DOUT defined if wires are unplugged
set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to spi_cs_n
set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to adc_dout
