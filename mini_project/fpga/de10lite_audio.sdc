# de10lite_audio.sdc -- timing constraints for Task 3
create_clock -name clk50 -period 20.000 [get_ports MAX10_CLK1_50]
derive_pll_clocks
derive_clock_uncertainty

# SPI pins, keys, switches and MCP3202 DOUT are asynchronous to clk50:
# they are double-registered inside the design.
set_false_path -from [get_ports {spi_sclk spi_mosi spi_cs_n adc_dout KEY[*] SW[*]}]

# Outputs are slow (<= 1 MHz toggling) or are re-timed by the receiver.
set_false_path -to [get_ports {spi_miso drdy fs_tick blk_tick adc_cs_n adc_sclk adc_din LEDR[*]}]
