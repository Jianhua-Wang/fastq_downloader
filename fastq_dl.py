from bs4 import BeautifulSoup
import requests
from ftplib import FTP
from subprocess import call
import argparse
import os



# # Try to get ENA FTP url

def get_ENA_url(srr_id):
    '''
    infer the ENA FTP url according the SRR (or ERR) id,
    if the file or files are archived by EBI, return the urls
    else return [].

    >>> get_ENA_url('ERR2365269')
    >>> ['ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR236/009/ERR2365269/ERR2365269_1.fastq.gz',
         'ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR236/009/ERR2365269/ERR2365269_2.fastq.gz']
    '''

    if len(srr_id) >= 10:
        ena_ftp_url = f'vol1/fastq/{srr_id[:6]}/0{int(srr_id[9:]):>02,d}/{srr_id}/'
    else:
        ena_ftp_url = f'vol1/fastq/{srr_id[:6]}/{srr_id}/'
    ftp = FTP()
    ftp.connect('ftp.sra.ebi.ac.uk',21)
    ftp.login()
    files = ftp.nlst(ena_ftp_url)
    ftp.quit()

    return [f'ftp://ftp.sra.ebi.ac.uk/{i}' for i in files]


# # Try to get url of original file from SRA

# In the new SRA, the original sequencing read file are also can be downloaded from Amazon S3 (i.e. ERR2365269).
#
# But this new feature is only avaliable for data submitted after later 2019.
#
# So I won't consider this approach in the short run.

def get_original_url(srr_id):
    '''
    Scrapy the url of original file.

    >>> get_original_url('ERR2365269')
    >>> ['http://ftp.sra.ebi.ac.uk/vol1/run/ERR236/ERR2365269/capt-cardio-1-R1.fastq.bz2',
         'http://ftp.sra.ebi.ac.uk/vol1/run/ERR236/ERR2365269/capt-cardio-1-R2.fastq.bz2']
    '''
    original_urls = []
    response = requests.get(
        f'https://trace.ncbi.nlm.nih.gov/Traces/sra/?run={srr_id}')
    soup = BeautifulSoup(response.content, 'lxml')
    for h2 in soup.select('h2'):
        if h2.text == 'Original format':
            original_urls = h2.parent.select('a')
            if len(original_urls) == 0:
                pass
            else:
                original_urls = [i.attrs['href'] for i in original_urls]
            break
    return original_urls


# # Download SRR

def download_srr(srr_id):
    '''
    if the file were archived by EBI, get the urls and download using axel with 20 threads.
    else using fasterq-dump.
    '''
    urls = get_ENA_url(srr_id)
    py_dir = os.path.split(os.path.realpath(__file__))[0]
    if len(urls) == 0:
        print(f'Download {srr_id} using fasterq-dump')
        call(
            f'{py_dir}/fasterq-dump --split-files {srr_id}',
            shell=True)
    else:
        print(f'Download {srr_id} using axel from ENA')
        for url in urls:
            axel_code = call(f'{py_dir}/axel -n 20 -a {url}', shell=True)
            if axel_code != 0:
                ascp_url = url.replace('ftp://ftp.sra.ebi.ac.uk','era-fasp@fasp.sra.ebi.ac.uk:')
                call(f'ascp -QT -l 300m -P 33001 -i ~/anaconda3/etc/asperaweb_id_dsa.openssh -k 1 {ascp_url}',shell=True)


# # Download SRX

def download_srx(srx_id):
    '''
    Get the SRR id under SRX and download SRR.

    Some SRXs contain more than one SRR (i.e. SRX5545333). Download the SRRs iteratively for these cases.

    [TODO] Merge the SRRs under same SRX.
    '''
    response = requests.get(f'https://www.ncbi.nlm.nih.gov/sra/?term={srx_id}')
    soup = BeautifulSoup(response.content, 'lxml')

    srr_id_list = [srr.text for srr in soup.select('table')[0].select('a')]

    if len(srr_id_list) == 0:
        print('Invalid SRX id!')
    elif len(srr_id_list) == 1:
        print(f'{srx_id} only has 1 run: {srr_id_list[0]}')
        print(f'Donwload {srr_id_list[0]}')
        download_srr(srr_id_list[0])
    else:
        print(f'There {len(srr_id_list)} runs in {srx_id}')
        for ith, srr_id in enumerate(srr_id_list):
            print(f'Download No.{ith+1}: {srr_id}')
            download_srr(srr_id)

# # Download SRP



# # Download GSM

def download_gsm(gsm_id):
    '''
    get SRX from GSM and download SRR
    '''
    response = requests.get(
        f'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gsm_id}')
    soup = BeautifulSoup(response.content, 'lxml')

    srx_id = None
    for a in soup.select('a'):
        if a.text.startswith('SRX'):
            srx_id = a.text

    if srx_id:
        print(f'{gsm_id} corresponds to {srx_id}')
        download_srx(srx_id)
    else:
        print('Invalid GSM id!')


# # Download GSE


def download_gse(gse_id):
    '''
    Scrapy GSM ids from https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=gse_id
    and download GSM
    
    [TODO] Split by super GSE and sub GSE
    '''
    response = requests.get(
        f'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse_id}')
    soup = BeautifulSoup(response.content, 'lxml')

    gsm_list = []
    for a in soup.select('a'):
        if a.text.startswith('GSM'):
            gsm_list.append(a.text)

    if len(gsm_list) == 0:
        print('Invalid GSE id!')
    elif len(gsm_list) == 1:
        print(f'{gse_id} only has 1 sample: {gsm_list[0]}')
        print(f'Search SRX for {gsm_list[0]}')
        download_gsm(gsm_list[0])
    else:
        print(f'There {len(gsm_list)} runs in {gse_id}')
        for ith, gsm_id in enumerate(gsm_list):
            print(f'Search SRX for No.{ith+1}: {gsm_id}')
            download_gsm(gsm_id)


def download_accession(accession):
    print(f'Start processing {accession}')
    if accession.startswith('SRR'):
        download_srr(accession)
    elif accession.startswith('SRX'):
        download_srx(accession)
    elif accession.startswith('GSM'):
        download_gsm(accession)
    elif accession.startswith('GSE'):
        download_gse(accession)
    else:
        print('Invalid Accession!')


def print_logo():
    logo = '''
========================================================================
     \033[1;33m/\\\033[0m
    \033[1;33m/__\\\033[0m\033[1;31m\\\033[0m            Download SRA and GEO fastq, simple and faster
   \033[1;33m/\033[0m  \033[1;31m---\\\033[0m
  \033[1;33m/\\\033[0m      \033[1;31m\\\033[0m          Author: Jianhua Wang
 \033[1;33m/\033[0m\033[1;32m/\\\033[0m\033[1;33m\\\033[0m     \033[1;31m/\\\033[0m         Date:   08-12-2020
 \033[1;32m/  \   /\033[0m\033[1;31m/__\\\033[0m
\033[1;32m`----`-----\033[0m
========================================================================
    '''
    print(logo)

def parseArguments():
    parser = argparse.ArgumentParser(usage="python fastq_dl.py SRR9595574",description="Given a GSE, GSM, SRX, or SRR accession and download the fastq files",)
    parser.add_argument('Accession', nargs='?', type=str, help='GEO or SRA Accession, i.e. SRR9595574, SRX2577854, GSM2496146, or GSE87254. Use "," to specify more than one Accession'),
    parser.add_argument('-f','--file', type=str, help='Accession list file',metavar=''),
    args = parser.parse_args()
    return args

def main():
    if args.file:
        accession_list = open(args.file,'r')
        accession_list = accession_list.readlines()
        for accession in accession_list:
            download_accession(accession.strip())
    else:
        for accession in args.Accession.split(','):
            download_accession(accession)


if __name__ == '__main__':
    print_logo()
    args = parseArguments()
    main()
