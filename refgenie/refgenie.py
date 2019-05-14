#!/usr/bin/env python


from argparse import ArgumentParser
import attmap
import pypiper
import yaml
import os
import re
import sys
import urllib
from ._version import __version__

class RefGenomeConfiguration(attmap.PathExAttMap):

    def get_index(self, genome_name, index_name):
        if not genome_name in self.refgenomes:
            msg = "Your genomes do not include {}".format(genome_name)
            raise MissingGenomeError(msg)

        if not index_name in self.refgenomes[genome_name]:
            msg = "Genome {} exists, but index {} is missing".format(genome_name, index_name)
            raise MissingIndexError(msg)

            return self.refgenomes[genome_name][index_name]

    def list_genomes(self):
        return list(self.refgenomes.keys())


    def list_indexes(self):
        string = ""
        for genome, value in self.refgenomes.items():
            string += "  {}: {}\n".format(genome, "; ".join(list(value.indexes)))
        return string

    def to_yaml(self):
        ## TODO: use a recursive dict function for attmap representation
        try:
            return yaml.dump(self.__dict__, default_flow_style=False)
        except yaml.representer.RepresenterError:
            print("SERIALIZED SAMPLE DATA: {}".format(self))
            raise


def is_url(url):
    return urllib.parse(url).scheme != ""


class _VersionInHelpParser(ArgumentParser):
    def format_help(self):
        """ Add version information to help text. """
        return "version: {}\n".format(__version__) + \
               super(_VersionInHelpParser, self).format_help()



def build_argparser():
    """
    Builds argument parser.

    :return argparse.ArgumentParser
    """

    banner = "%(prog)s - builds and manages reference genome assemblies"
    additional_description = "\nhttps://refgenie.databio.org"

    parser = _VersionInHelpParser(
            description=banner,
            epilog=additional_description)


    parser.add_argument(
            "-V", "--version",
            action="version",
            version="%(prog)s {v}".format(v=__version__))

    subparsers = parser.add_subparsers(dest="command") 

    def add_subparser(cmd, description):
        return subparsers.add_parser(
            cmd, description=description, help=description)

    subparser_messages = {
        "build": "Build genome indexes",
        "list": "List available local genomes.",
        "pull": "Download indexes.",
        "avail": "List available genomes and indexes on server.",
    }

    sps = {}
    for cmd, desc in subparser_messages.items():
        sps[cmd] = add_subparser(cmd, desc)

    sps["build"] = pypiper.add_pypiper_args(sps["build"], groups=None, args=["recover", "config"])

    default_config = os.path.splitext(os.path.basename(sys.argv[0]))[0] + ".yaml"
    # Arguments to optimize the interface to looper

    # Add any pipeline-specific arguments
    sps["build"].add_argument('-i', '--input', dest='input', required = True,
        help='Local path or URL to genome sequence file in .fa, .fa.gz, or .2bit format.')

    sps["build"].add_argument('-n', '--name', dest='name', required = False,
        help='Name of the genome to build. If ommitted, refgenie will use'
        'the basename of the file specified in --input')

    sps["build"].add_argument('-a', '--annotation', dest='annotation', required = False,
        help='Path to GTF gene annotation file')

    sps["build"].add_argument("-d", "--docker", action="store_true",
        help="Run all commands in the refgenie docker container.")

    # Don't error if RESOURCES is not set.
    try:
        # First priority: GENOMES variable
        genome_folder = os.environ["GENOMES"]
    except:
        try:
            # Second priority: RESOURCES/genomes
            genome_folder = os.path.join(os.environ["RESOURCES"], "genomes")
        except:
            # Otherwise, current directory
            genome_folder = ""

    sps["build"].add_argument('-o', '--outfolder', dest='outfolder', required = False,
        default=genome_folder,
        help='Path to genomes folder, using the $GENOMES environment variable'
        ' if set. Currently set to: \'{}\''.format(
            genome_folder))

    sps["list"].add_argument('-g', '--genome-folder', required = False,
        default=genome_folder,
        help='Path to genomes folder, using the $GENOMES environment variable'
        ' if set. Currently set to: \'{}\''.format(
            genome_folder))

    sps["pull"].add_argument('-g', '--genome', default="hg38")
    sps["pull"].add_argument('-i', '--index', default="bowtie2")


    genome_config = os.path.join(genome_folder, "refgenie.yaml")
    sps["list"].add_argument("-c", "--genome-config",
        default=genome_config)

    return parser


def copy_or_download_file(input_string, outfolder):
    """
    Given an input file, which can be a local file or a URL, and output folder, 
    this downloads or copies the file into the output folder.
    @param input_string: Can be either a URL or a path to a local file
    @type input_string: str
    @param outfolder: Where to store the result.
    """
    result_file = os.path.join(outfolder, os.path.basename(input_string))

    if is_url(input_string):
        cmd = "wget -O " + result_file + " " + input_string
    else:
        cmd = "cp " + input_string + " " + result_file
    return([result_file, cmd])

def convert_file(input_file, output_file, conversions):
    """
    Given an input file, output file, and a list of conversions, gives the appropriate output file.
    @param output_file: Path to local output file you want to create
    @param conversions: A dictionary of shell commands to convert files of a given type.
    @type conversions: dict
    """
    form = {"INPUT": input_file, "OUTPUT": output_file}
    ext = os.path.splitext(input_file)[1]
    if ext in conversions:
        cmd = conversions[ext].format(**form)
        return(cmd)
    else:
        # No conversion available/necessary.
        return None


def default_config_file():
    """
    Path to default compute environment settings file.
    
    :return str: Path to default compute settings file
    """
    return os.path.join(os.path.dirname(__file__), "refgenie.yaml")


def build_indexes(args):

    if args.name:
        genome_name = args.name
    else:
        genome_name = os.path.basename(args.input)
        # eliminate extensions to get canonical genome name.
        for strike in [".fasta.gz$", ".fa.gz$", ".fasta$", ".fa$", ".gz$", ".2bit$"]:
            genome_name = re.sub(strike, "", genome_name)

    print("Using genome name: {}".format(genome_name))
    outfolder = os.path.join(args.outfolder, genome_name)
    outfolder = os.path.abspath(outfolder)
    print("Output to: " , genome_name, args.outfolder, outfolder)

    print(default_config_file())

    config_file = args.config_file
    import logging
    if config_file:
        if os.path.isfile(config_file):
            #looks good!
            pass
        else:
            logging.debug("Config file path isn't a file: {}".
                          format(config_file))
            args.config_file = default_config_file()

    pm = pypiper.PipelineManager(name="refgenie", outfolder=outfolder, args=args)
    ngstk = pypiper.NGSTk(pm = pm)
    tools = pm.config.tools  # Convenience alias
    index = pm.config.index
    param = pm.config.param

    #pm.make_sure_path_exists(outfolder)
    conversions = {}
    conversions[".2bit"] = "twoBitToFa {INPUT} {OUTPUT}"
    conversions[".gz"] = ngstk.ziptool + " -cd {INPUT} > {OUTPUT}"

    # Copy fasta file to genome folder structure
    local_raw_fasta = genome_name + ".fa"
    raw_fasta = os.path.join(outfolder, local_raw_fasta)

    input_file = os.path.join(outfolder, os.path.basename(args.input))

    input_file, cmd = copy_or_download_file(args.input, outfolder)
    pm.run(cmd, input_file)

    container = None
    if args.docker:
        # Set up some docker stuff
        pm.get_container("nsheff/refgenie", outfolder)
        # of = os.path.abspath(outfolder)
        # outfolder = of
        # cmd = "docker run -itd"
        # cmd += " -v " + of + ":" + of
        # cmd += " nsheff/refgenie"
        # container = pm.checkprint(cmd).rstrip()
        # print("Using docker container: " + container)
        # pm.atexit_register(remove_container, container)

    cmd = convert_file(input_file, raw_fasta, conversions)
    if cmd:
        pm.run(cmd, raw_fasta, container=pm.container)

    cmd = tools.samtools + " faidx " + raw_fasta
    pm.run(cmd, raw_fasta + ".fai", container=pm.container)

    # Determine chromosome sizes
    fai_file = raw_fasta + ".fai"
    # symlinks should be relative so folders are portable.
    loc_chrom_sizes_file = genome_name + ".chrom.sizes"
    chrom_sizes_file = os.path.join(outfolder, loc_chrom_sizes_file)
    chrom_sizes_alias = os.path.join(outfolder, genome_name + ".chromSizes")
    cmd = "cut -f 1,2 " + fai_file + " > " + chrom_sizes_file
    cmd2 = "ln -s " + loc_chrom_sizes_file + " " + chrom_sizes_alias
    pm.run([cmd, cmd2], chrom_sizes_alias, container=pm.container)

    # Copy annotation file (if any) to folder structure
    if args.annotation:
        annotation_file_unzipped = os.path.join(outfolder, genome_name + ".gtf")
        annotation_file, cmd = copy_or_download_file(args.annotation, outfolder)
        pm.run(cmd, annotation_file)

        cmd = convert_file(annotation_file, annotation_file_unzipped, conversions)
        pm.run(cmd, annotation_file_unzipped)

    #   cmd = "cp " + args.annotation + " " + annotation_file
    #   cmd2 = ngstk.ziptool + " -d " + annotation_file 
    #   pm.run([cmd, cmd2], annotation_file_unzipped)

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
        pm.run([cmd1, cmd2, cmd3], target, container=pm.container)

    # Bismark index - bowtie2
    if index.bismark_bt2:
        folder = os.path.join(outfolder, "indexed_bismark_bt2")
        ngstk.make_dir(folder)
        target = os.path.join(folder, "completed.flag")
        cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
        cmd2 = tools.bismark_genome_preparation + " --bowtie2 " + folder
        cmd3 = "touch " + target
        pm.run([cmd1, cmd2, cmd3], target, container=pm.container)

    # Bismark index - bowtie1
    if index.bismark_bt1:
        folder = os.path.join(outfolder, "indexed_bismark_bt1")
        ngstk.make_dir(folder)
        target = os.path.join(folder, "completed.flag")
        cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
        cmd2 = tools.bismark_genome_preparation + " " + folder
        cmd3 = "touch " + target
        pm.run([cmd1, cmd2, cmd3], target, container=pm.container)

    # Epilog meth calling
    if index.epilog:
        folder = os.path.join(outfolder, "indexed_epilog")
        ngstk.make_dir(folder)
        target = os.path.join(folder, "completed.flag")
        cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
        cmd2 = tools.epilog_indexer + " -i " + raw_fasta
        cmd2 += " -o " + os.path.join(folder, genome_name + "_" + param.epilog.context + ".tsv")
        cmd2 += " -s " + param.epilog.context  #context
        cmd2 += " -t"
        cmd3 = "touch " + target
        pm.run([cmd1, cmd2, cmd3], target, container=pm.container)

    if index.hisat2:
        folder = os.path.join(outfolder, "indexed_hisat2")
        ngstk.make_dir(folder)
        target = os.path.join(folder, "completed.flag")
        cmd1 = "ln -sf ../" + local_raw_fasta + " " + folder
        cmd2 = tools.hisat2build + " " + raw_fasta + " " + os.path.join(folder, genome_name)
        cmd3 = "touch " + target
        pm.run([cmd1, cmd2, cmd3], target, container=pm.container)

    # Kallisto should index transcriptome
    # So it doesn't make sense to run these at the same time as the others.
    if index.kallisto:
        folder = os.path.join(outfolder, "indexed_kallisto")
        ngstk.make_dir(folder)
        target = os.path.join(folder, "completed.flag")
        cmd2 = tools.kallisto + " index -i " + os.path.join(folder, genome_name + "_kallisto_index.idx")
        cmd2 += " " + raw_fasta
        cmd3 = "touch " + target
        pm.run([cmd2, cmd3], target, container=pm.container)

    pm.stop_pipeline()


def load_yaml(filename):
    import yaml
    with open(filename, 'r') as f:
        data = yaml.load(f, yaml.SafeLoader)
    return data


def pull_index(genome, asset, genome_folder=None):

    import urllib.request
    import shutil

    url = "http://big.databio.org/example_data/rCRS.fa.gz"

    base = "http://big.databio.org/"
    base = "http://localhost/asset"
    url = "{base}/{genome}/{asset}".format(base=base, genome=genome, asset=asset)

    # local file to save as
    file_name = "{genome_folder}/{genome}/{asset}.tar".format(
        genome_folder=genome_folder,
        genome=genome,
        asset=asset)

    # Download the file from `url` and save it locally under `file_name`:
    print("Downloading {}...".format(url))
    with urllib.request.urlopen(url) as response, open(file_name, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)
    print("Download complete.")
    print("Saved as: {}".format(file_name))




def main():
    """ Primary workflow """


    parser = build_argparser()
    args, remaining_args = parser.parse_known_args()

    if args.command == "build":
        build_indexes(args)

    if args.command == "list":
        print("Local reference genomes")

        rgc = RefGenomeConfiguration(load_yaml(args.genome_config))

        print(rgc)

        print("Genomes: {}".format(rgc.list_genomes()))
        print("Indexes:\n{}".format(rgc.list_indexes()))

        print(rgc.to_yaml())


    if args.command == "pull":
        print("Pull genome: {}; index: {}".format(args.genome, args.index))
        pull_index(args.genome, args.index)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Program canceled by user!")
        sys.exit(1)


