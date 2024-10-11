import io
import json
import os
import time
from datetime import datetime
import pandas as pd
import pandasql as ps
import requests
import logging
from driver_library_{{ org_name }}_{{ venture_name }}.driver_library.utils.s3.s3_object_store import S3
from driver_library_{{ org_name }}_{{ venture_name }}.driver_library.utils.converters.edgarhtml2text import HTMLiXBRL2Text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(funcName)s line# %(lineno)d: %(message)s')

class Constants:
    DRIVER_NAME = "Edgar"  # must match postgres database lookup table
    APPLICATION_NAME = DRIVER_NAME
    TICKET_URL = "https://www.sec.gov/include/ticker.txt"
    s3_EDGAR_KEY = "raw/edgar/{}/{}"
    API_URL = "https://data.sec.gov/{}/{}"
    category_endpoint = "submissions"
    DOWNLOAD_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{}/{}/{}"
    RATE_LIMIT_HIT_COUNT = 100
    RATE_LIMIT_SLEEP_SECS = 120
    PROCESS_FORM_QUERY = """SELECT * FROM main_df WHERE form='{}' AND filingDate BETWEEN '{}' AND '{}' order by filingDate asc"""
    COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"


class Driver:
    def __init__(self, args):
        self.ticker_url = Constants.TICKET_URL
        self.from_date = args["from_date"]
        self.to_date = args["to_date"]
        self.form_type = args["form_type"]
        self.bucket = args["bucket"]
        self.user_agent = args["user_agent"]
        self.year = args["to_date"].split('-')[0]
        self.key_value_pairs = None
        self.args = args
        self.docs_10K = 0
        self.docs_10Q = 0


    def build_api_url(self, category, filename):
        """
        Module to construct the DATA SEC API URL
        """
        return Constants.API_URL.format(category, filename)

    def get_ticker_details(self):
        """
        Module to fetch ticker data from the Ticker URL
        :return: downloaded ticker data
        """
        done_file = 'done.txt'
        done_ciks = set()

        if os.path.exists(done_file):
            with open(done_file, 'r') as f:
                done_ciks = set(f.read().splitlines())

        headers = {
            'cache-control': "no-cache",
            'User-Agent': self.user_agent
        }
        response = requests.get(self.ticker_url, headers=headers)
        ticker_data = pd.read_csv(io.StringIO(response.text), sep="\t", header=None)
        ticker_data = ticker_data.drop_duplicates(subset=1)
        ticker_data = ticker_data.sort_values(by=1)
        ticker_data = ticker_data[~ticker_data[1].astype(str).isin(done_ciks)]
        return ticker_data

    def process_submissions(self, ticker_details):
        """
        Downloading form data from the Submissions endpoint: "https://data.sec.gov/submissions/CIK001.json"
        :param ticker_details: contains CIK ID
        :return:
        """
        hit_count = 0
        for index, row in ticker_details.iterrows():
            cikid = str(row[1]).zfill(10)
            json_filename = f"CIK{cikid}.json"
            base_url = self.build_api_url(Constants.category_endpoint, json_filename)

            headers = {
                'cache-control': "no-cache",
                'User-Agent': self.user_agent
            }

            response = requests.get(base_url, headers=headers)
            self.process_form_details(response, cikid)
            hit_count += 1

            if hit_count % Constants.RATE_LIMIT_HIT_COUNT == 0:
                logger.info("Sleeping for 2 minutes to rate limit...")
                time.sleep(Constants.RATE_LIMIT_SLEEP_SECS)

    def upload_to_s3(self, local_file_name, s3_key):
        """
        Helper module to upload data/files to s3
        :param local_file_name: file to be uploaded
        :param s3_key: s3 dir details to save
        :return:
        """

        s3 = S3()

        try:
            if not os.path.exists(local_file_name):
                raise FileNotFoundError(f"File '{local_file_name}' does not exist.")

            s3.authenticate()
            s3.upload_file(local_file_name, self.bucket, s3_key)
            logger.info(f'Uploaded local_file_name: {local_file_name}, S3 bucket: s3://{self.bucket}/{s3_key}')

        except Exception as e:
            logger.error(f"Error uploading data to S3 bucket: {str(e)}")

    def download_files(self, row, cik):
        """
        Module to download forms, convert to HTML format, saving data to s3
        :param row: contains details as accessionNumber, filingDate, filepath...
        :param cik: Central Index Key; used to identify filings of a company/entity
        """
        base_url = Constants.DOWNLOAD_BASE_URL.format(cik, row['accessionNumber'].replace('-', ''),
                                                      row['primaryDocument'])
        headers = {
            'cache-control': "no-cache",
            'User-Agent': self.user_agent
        }
        response = requests.get(base_url, headers=headers)
        file_content = response.content

        file_path = f"{row['primaryDocument']}"
        filing_date = row['filingDate'].strftime("%Y-%m-%d")

        filing_year = "Not_Available"
        if filing_date != '':
            date_filed = datetime.strptime(filing_date, "%Y-%m-%d")
            filing_year = date_filed.year

        s3_root = Constants.s3_EDGAR_KEY.format(self.form_type, filing_year)

        logger.info(f' ==  New document with filing date = {filing_date}')
        logger.info(f' ==  Filing year = {filing_year}')
        logger.info(f' ==  s3 key root to be used = {s3_root}')

        with open(file_path, "wb") as f:
            f.write(file_content)

        split_tup = str(row['primaryDocument']).split('.')
        file_extension = split_tup[1].lower()
        text_file_path = split_tup[0] + ".txt"

        if self.form_type == '10-Q' and filing_date != '':
            filing_dt = datetime.strptime(filing_date, "%Y-%m-%d")
            filing_month = filing_dt.month
            filing_quarter = ''
            if filing_month in [1, 2, 3]:
                filing_quarter = 'Q1'
            elif filing_month in [4, 5, 6]:
                filing_quarter = 'Q2'
            elif filing_month in [7, 8, 9]:
                filing_quarter = 'Q3'
            elif filing_month in [10, 11, 12]:
                filing_quarter = 'Q4'
            else:
                filing_quarter = 'Invalid_month'

            self.docs_10Q += 1
            s3_key = f"{s3_root}/{filing_quarter}/{cik.lstrip('0')}/{text_file_path}"
            logger.info(f' ==  10-Q s3 key = {s3_key}')

        else:
            self.docs_10K += 1
            s3_key = f"{s3_root}/{cik.lstrip('0')}/{text_file_path}"
            logger.info(f' ==  10-K s3 key = {s3_key}')

        if file_extension == "htm" or file_extension == "html":

            html_converter = HTMLiXBRL2Text()
            html_converter.configure(file_path, text_file_path)
            success = html_converter.convert()

            logger.info(f'file conversion status = {success}, original = {file_path} text = {text_file_path}')

            if not success:
                logger.error(f"Failed to convert file {file_path}")
            if success:
                if os.path.isfile(text_file_path):
                    logger.info(f's3 file upload key = {s3_key}, file = {text_file_path}')
                    self.upload_to_s3(text_file_path, s3_key)

                if os.path.isfile(file_path):
                    if self.form_type == '10-Q' and filing_date != '':
                        filing_dt = datetime.strptime(filing_date, "%Y-%m-%d")
                        filing_month = filing_dt.month
                        filing_quarter = ''

                        if filing_month in [1,2,3]:
                            filing_quarter = 'Q1'
                        elif filing_month in [4,5,6]:
                            filing_quarter = 'Q2'
                        elif filing_month in [7,8,9]:
                            filing_quarter = 'Q3'
                        elif filing_month in [10,11,12]:
                            filing_quarter = 'Q4'
                        else:
                            filing_quarter = 'Invalid_month'

                        s3_key_pd = f"{s3_root}/{filing_quarter}/{cik.lstrip('0')}/{row['primaryDocument']}"
                        self.key_value_pairs['Filing Date'] = filing_date
                        metadata_json_object = json.dumps(self.key_value_pairs, indent=4)
                        metadata_filename = f"{cik}.metadata"

                        with open(metadata_filename, "w") as outfile:
                            outfile.write(metadata_json_object)

                        s3_key_meta = f"{s3_root}/{filing_quarter}/{cik.lstrip('0')}/{metadata_filename}"

                        self.upload_to_s3(metadata_filename, s3_key_meta)

                    else:
                        s3_key_pd = f"{s3_root}/{cik.lstrip('0')}/{row['primaryDocument']}"

                    logger.info(f"Uploading to s3 with.. file_path: {file_path}, s3_key_pd: {s3_key_pd}")
                    self.upload_to_s3(file_path, s3_key_pd)

                if os.path.isfile(file_path):
                    os.remove(file_path)
                if os.path.isfile(text_file_path):
                    os.remove(text_file_path)
        else:
            logger.warning('File extension is not html')

        with open('done.txt', 'a') as f:
            f.write(cik.lstrip('0') + '\n')

    def process_form_details(self, main_dec_res, cikid):
        """
        Module to process and save metadata of the filings like company_name, cik, category, filing date...
        """
        main_json = main_dec_res.json()
        main_details_json = main_json["filings"]["recent"]

        main_df = pd.DataFrame.from_dict(main_details_json)
        main_df['filingDate'] = pd.to_datetime(main_df['filingDate'], format='%Y-%m-%d')

        from_date = datetime.strptime(self.from_date, '%Y-%m-%d')
        to_date = datetime.strptime(self.to_date, '%Y-%m-%d')

        query = Constants.PROCESS_FORM_QUERY.format(self.form_type, from_date, to_date)
        filtered_df = ps.sqldf(query)

        if not filtered_df.empty:
            filtered_df['filingDate'] = pd.to_datetime(filtered_df['filingDate'])
            date_str = filtered_df['filingDate'].dt.strftime('%Y-%m-%d').iloc[0]
            self.key_value_pairs = {
                'Company Name': main_json['name'],
                'Company cik': main_json['cik'],
                'entity type': main_json['entityType'],
                'Sic': main_json['sic'],
                'Sic Description': main_json['sicDescription'],
                'Category': main_json['category'],
                'Fiscal Year End': main_json['fiscalYearEnd'],
                'Addresses': main_json['addresses'],
                'Filing Date': date_str
            }

            filtered_df.apply(self.download_files, cik=cikid, axis=1)
            metadata_json_object = json.dumps(self.key_value_pairs, indent=4)

            if self.form_type != '10-Q':
                metadata_filename = f"{cikid}.metadata"
                with open(metadata_filename, "w") as outfile:
                    outfile.write(metadata_json_object)

                filing_year = "Not_Available"
                if date_str != '':
                    date_filed = datetime.strptime(date_str, "%Y-%m-%d")
                    filing_year = date_filed.year

                s3_root = Constants.s3_EDGAR_KEY.format(self.form_type, filing_year)

                s3_key = f"{s3_root}/{cikid.lstrip('0')}/{metadata_filename}"
                logger.info(f' ==  Metadata s3 key = {s3_key}')

                self.upload_to_s3(metadata_filename, s3_key)

                os.remove(metadata_filename)
                with open('done.txt', 'a') as f:
                    f.write(cikid.lstrip('0') + '\n')
        else:
            logger.info("No rows matching the query for form-type: {}, dates: {} - {}"
                        .format(self.form_type, from_date, to_date))

        logger.info(f' ==  Edgar driver run for cik {cikid} completed.')
        logger.info(f' ==  Total 10-Ks = {self.docs_10K}, Total 10-Qs = {self.docs_10Q}')


def submit(input_args):

    if 'cik' in input_args:
        companyList = []
        companyList.append('CMPNY')
        companyList.append(input_args['cik'])
        df_cik = pd.DataFrame([companyList])
        sec_gov = Driver(input_args)
        sec_gov.process_submissions(df_cik)

    elif 'ticker' in input_args:
        companyList = []
        companyName = str(input_args['ticker']).upper()
        sec_gov = Driver(input_args)
        headers = {
            'cache-control': "no-cache",
            'User-Agent': sec_gov.user_agent
        }
        companyCik = requests.get(
            Constants.COMPANY_TICKERS,
            headers=headers
        )
        jsonList = json.loads(json.dumps(companyCik.json()))
        df_ticker_cik = 0
        for k, v in jsonList.items():
            if companyName in str(v):
                cik_str = v['cik_str']
                companyList.append(companyName)
                companyList.append(cik_str)
                df_ticker_cik = pd.DataFrame([companyList])

        sec_gov = Driver(input_args)
        sec_gov.process_submissions(df_ticker_cik)

    elif 'cik_array' in input_args:
        df = pd.DataFrame(input_args['cik_array'].split(r"[,\s]+"))
        for x in df[1]:
            companyList = []
            companyList.append('CMPNY')
            companyList.append(x)
            df_cik = pd.DataFrame([companyList])
            sec_gov = Driver(input_args)
            sec_gov.process_submissions(df_cik)
    else:
        sec_gov = Driver(input_args)
        ticker_details = sec_gov.get_ticker_details()
        sec_gov.process_submissions(ticker_details)
