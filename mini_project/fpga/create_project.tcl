# =============================================================================
# create_project.tcl  --  builds the Task 3 Quartus project for the DE10-Lite
#
# Usage (Quartus Prime Lite, from this folder):
#     quartus_sh -t create_project.tcl            (MCP3202, default)
#     quartus_sh -t create_project.tcl 1          (MAX 10 on-chip ADC)
#     quartus_sh -t create_project.tcl 2          (internal test tone)
#     quartus_sh -t create_project.tcl 0 3208     (external MCP3208 instead
#                                                  of MCP3202; also 3201, 3204, 3008, 3004)
#   then:  quartus_sh --flow compile task3_audio
#   or open task3_audio.qpf in the GUI and press "Start Compilation".
#
# Pin numbers are from the DE10-Lite User Manual (GPIO header JP1).
# Double-check them against your board's System Builder / manual.
# =============================================================================
set adc_select 0
set mcp_part   3202
# command-line arguments (absent when the script is 'source'd in the GUI Tcl console)
if { [info exists argc] && $argc > 0 } { set adc_select [lindex $argv 0] }
if { [info exists argc] && $argc > 1 } { set mcp_part   [lindex $argv 1] }

project_new task3_audio -overwrite
set_global_assignment -name FAMILY "MAX 10"
set_global_assignment -name DEVICE 10M50DAF484C7G
set_global_assignment -name TOP_LEVEL_ENTITY de10lite_audio_top
set_global_assignment -name VHDL_INPUT_VERSION VHDL_2008
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files

# ---------------------------------------------------------------- sources
set_global_assignment -name VHDL_FILE sample_tick_gen.vhd
set_global_assignment -name VHDL_FILE mcp3202_reader.vhd
set_global_assignment -name VHDL_FILE test_tone_gen.vhd
set_global_assignment -name VHDL_FILE audio_block_buffer.vhd
set_global_assignment -name VHDL_FILE spi_slave_block.vhd
set_global_assignment -name VHDL_FILE de10lite_audio_top.vhd
set_global_assignment -name SDC_FILE  de10lite_audio.sdc

if { $adc_select == 1 } {
  # MAX 10 ADC: wrapper + the two IP variants generated in the IP Catalog
  set_global_assignment -name VHDL_FILE max10_adc_sampler.vhd
  set_global_assignment -name QIP_FILE  adc_pll.qip
  set_global_assignment -name QIP_FILE  adc_core/synthesis/adc_core.qip
}

set_parameter -name ADC_SELECT $adc_select
set_parameter -name FS_HZ 16000
set_parameter -name ADDR_W 10
set_parameter -name MCP_PART $mcp_part
if { $mcp_part == 3201 } { set_parameter -name MCP_SCLK_HZ 800000 }

# ------------------------------------------------------------------- pins
source de10lite_pins.tcl

project_close
puts "Project task3_audio created (ADC_SELECT = $adc_select, MCP_PART = $mcp_part)"
