#!/usr/bin/env python

import pypiper
from argparse import ArgumentParser
import os, re
import urlparse

def is_url(url):
	return urlparse.urlparse(url).scheme != ""


parser = ArgumentParser(description='Pipeline')

#parser = pypiper.add_pypiper_args(parser, args = ["config"]) # new way
#old way: 
import sys
parser = pypiper.add_pypiper_args(parser)

default_config = os.path.splitext(os.path.basename(sys.argv[0]))[0] + ".yaml"
# Arguments to optimize the interface to looper
parser.add_argument(
	"-C", "--config", dest="config_file", type=str,
	help="pipeline config file in YAML format; relative paths are \
	considered relative to the pipeline script. \
	defaults to " + default_config,
	required=False, default=default_config, metavar="CONFIG_FILE")

# Add any pipeline-specific arguments
parser.add_argument('-input', '--input', dest='input', required = True,
	help='Local path or URL to genome sequence file in .fa or .2bit format.')

parser.add_argument('-n', '--name', dest='name', required = False,
	help='Name of the genome to build.')


parser.add_argument('-a', '--annotation', dest='annotation', required = False,
	help='Path to GTF gene annotation file')

# Don't error if RESOURCES is not set.
try:
	# First priority: GENOMES variable
	default_outfolder = os.environ["GENOMES"]
except:
	try:
		# Second priority: RESOURCES/genomes
		default_outfolder = os.path.join(os.environ["RESOURCES"], "genomes")
	except:
		# Otherwise, current directory
		default_outfolder = ""

parser.add_argument('-o', '--outfolder', dest='outfolder', required = False,
	default = default_outfolder,
	help='Path to output genomes folder')

args = parser.parse_args()

if args.name:
	genome_name = args.name
else:
	genome_name = os.path.basename(args.fasta)
	# eliminate extensions to get canonical genome name.
	for strike in [".fasta$", ".fa$", ".gz$", ".2bit$"]:
		genome_name = re.sub(strike, "", genome_name)


outfolder = os.path.join(args.outfolder, genome_name)
print("Output to: " , genome_name, args.outfolder, outfolder)

pm = pypiper.PipelineManager(name="build_reference", outfolder = outfolder, args = args)
ngstk = pypiper.NGSTk(pm = pm)
tools = pm.config.tools  # Convenience alias
index = pm.config.index

#pm.make_sure_path_exists(outfolder)
conversions = {}
conversions["2bit"] = "twoBitToFa {INPUT} {OUTPUT}"
conversions["gz"] = ngstk.ziptool + " -cd {INPUT} > {OUTPUT}"

def get_raw_file(input_string, output_file, conversions=conversions):
	"""
	Given an input file, output file, and a list of conversions, gives the appropriate output file.
	Also downloads if you give a URL.
	@param input_string: Can be either a URL or a path to a local file
	@type input_string: str
	@param output_file: Path to local output file you want to create
	@param conversions: A dictionary of shell commands to convert files of a given type.
	@type conversions: dict
	"""
	input_file = os.path.join(outfolder, os.path.basename(input_string))
	print("input:" + input_file + " output:" + output_file)
	form = {"INPUT": input_file, "OUTPUT": output_file}
	if is_url(input_string):
		cmd = "wget -O " + input_file + " " + input_string
	else:
		cmd = "cp " + input_string + " " + input_file

	
	ext = os.path.splitext(input_file)[1]
	try:
		cmd2 = conversions[ext].format(**form)
	else:
		cmd2 = None
	
	return([cmd, cmd2])

# Copy fasta file to genome folder structure
local_raw_fasta = genome_name + ".fa"
raw_fasta = os.path.join(outfolder, local_raw_fasta)

input_file = os.path.join(outfolder, os.path.basename(args.input))

cmdlist = get_raw_file(args.input, raw_fasta)
pm.run(cmdlist, raw_fasta)

cmd = tools.samtools + " faidx " + raw_fasta
pm.run(cmd, raw_fasta + ".fai")

# Determine chromosome sizes
fai_file = raw_fasta + ".fai"
# symlinks should be relative so folders are portable.
loc_chrom_sizes_file = genome_name + ".chrom.sizes"
chrom_sizes_file = os.path.join(outfolder, loc_chrom_sizes_file)
chrom_sizes_alias = os.path.join(outfolder, genome_name + ".chromSizes")
cmd = "cut -f 1,2 " + fai_file + " > " + chrom_sizes_file
cmd2 = "ln -s " + loc_chrom_sizes_file + " " + chrom_sizes_alias
pm.run([cmd, cmd2], chrom_sizes_alias)

# Copy annotation file (if any) to folder structure
if args.annotation:

	annotation_file = os.path.join(outfolder, genome_name + ".gtf.gz")
	annotation_file_unzipped = os.path.join(outfolder, genome_name + ".gtf")
	cmdlist = get_raw_file(args.annotation, annotation_file_unzipped)
	pm.run(cmdlist, annotation_file_unzipped)

#	cmd = "cp " + args.annotation + " " + annotation_file
#	cmd2 = ngstk.ziptool + " -d " + annotation_file 
#	pm.run([cmd, cmd2], annotation_file_unzipped)

else:
	print("* No GTF gene annotations provided. Skipping this step.")


# Bowtie indexes
if index.bowtie2:
	folder = os.path.join(outfolder, "indexed_bowtie2")
	ngstk.make_dir(folder)
	target = os.path.join(folder, "completed.flag")
	cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
	cmd2 = tools.bowtie2build + " " + raw_fasta + " " + os.path.join(folder, genome_name)
	cmd3 = "touch " + target
	pm.run([cmd1, cmd2, cmd3], target)

# Bismark index - bowtie2
if index.bismark_bt2:
	folder = os.path.join(outfolder, "indexed_bismark_bt2")
	ngstk.make_dir(folder)
	target = os.path.join(folder, "completed.flag")
	cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
	cmd2 = tools.bismark_genome_preparation + " --bowtie2 " + folder
	cmd3 = "touch " + target
	pm.run([cmd1, cmd2, cmd3], target)

# Bismark index - bowtie1
if index.bismark_bt1:
	folder = os.path.join(outfolder, "indexed_bismark_bt1")
	ngstk.make_dir(folder)
	target = os.path.join(folder, "completed.flag")
	cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
	cmd2 = tools.bismark_genome_preparation + " " + folder
	cmd3 = "touch " + target
	pm.run([cmd1, cmd2, cmd3], target)

# Epilog meth calling
if index.epilog:
	folder = os.path.join(outfolder, "indexed_epilog")
	ngstk.make_dir(folder)
	target = os.path.join(folder, "completed.flag")
	cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
	cmd2 = tools.epilog_indexer + " -i " + raw_fasta
	cmd2 += " -o " + os.path.join(folder, genome_name + "_cg.tsv")
	cmd2 += " -s CG -t"
	cmd3 = "touch " + target
	pm.run([cmd1, cmd2, cmd3], target)

if index.kallisto:
	folder = os.path.join(outfolder, "indexed_kallisto")
	ngstk.make_dir(folder)
	target = os.path.join(folder, "completed.flag")
	cmd2 = tools.kallisto + " index -i " + os.path.join(folder, genome_name + "_kallisto_index.idx")
	cmd2 += " " + raw_fasta
	cmd3 = "touch " + target
	pm.run([cmd2, cmd3], target)

pm.stop_pipeline()