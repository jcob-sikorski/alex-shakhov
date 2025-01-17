# Standard library and third-party imports for core functionality
from dotenv import load_dotenv  # For loading environment variables
import os  # For file and directory operations
import imaplib  # For IMAP email access
import email  # For email parsing
from email import policy
from email.header import decode_header  # For decoding email headers
import datetime  # For timestamp handling
import xml.etree.ElementTree as ET  # For XML parsing
from typing import Dict, Any, Optional  # Type hints
from analyzer import DMARCAnalyzer, process_dmarc_report, save_reports  # Custom DMARC analysis
import logging  # For application logging
import argparse
import functools
import time
import socket
import ssl
from glob import glob
import json
import sys
import inspect
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dmarc_processing.log'),
        logging.StreamHandler()
    ]
)

def debug_print_var(var, var_name, logger=None):
    """
    Print detailed information about a variable including its name, type, and content.
    
    Args:
        var: The variable to inspect
        var_name: Name of the variable
        logger: Optional logger instance for structured logging
    """
    var_type = type(var).__name__
    var_content = str(var)
    
    # Truncate long content for readability
    if len(var_content) > 200:
        var_content = var_content[:200] + "..."
    
    debug_info = f"Variable: {var_name}\nType: {var_type}\nContent: {var_content}\n"
    
    if logger:
        logger.debug(debug_info)
    else:
        print(debug_info)

def setup_logging():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f'dmarc_fetch_{timestamp}.log'
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG to show all variable information
        handlers=[file_handler, console_handler]
    )
    
    logger = logging.getLogger(__name__)
    debug_print_var(log_filename, 'log_filename', logger)
    debug_print_var(formatter, 'formatter', logger)
    return logger

def parse_imap_search_result(data):
    """Parse IMAP search results, handling iCloud's specific format."""
    logger = logging.getLogger(__name__)
    debug_print_var(data, 'data', logger)
    
    if not data[0]:
        return []
    
    number_strings = data[0].decode('ascii').split()
    debug_print_var(number_strings, 'number_strings', logger)
    
    result = [int(num) for num in number_strings]
    debug_print_var(result, 'result', logger)
    return result

def process_fetch_response(msg_data):
    """
    Process IMAP FETCH response, handling both standard and flag-included formats.
    
    Args:
        msg_data: Raw FETCH response from IMAP server
    
    Returns:
        bytes: Email body data if found, None otherwise
    """
    if not msg_data:
        return None
        
    # Handle standard format
    if len(msg_data) == 1 and isinstance(msg_data[0], tuple):
        return msg_data[0][1]
        
    # Handle format with flags
    for item in msg_data:
        if isinstance(item, tuple) and len(item) > 1:
            return item[1]
            
    return None

def clean_reports_directory(directory):
    """
    Recursively remove the dmarc reports directory and all its contents.
    
    Args:
        directory: Path to the directory to be removed
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Cleaning directory: {directory}")
    
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info(f"Successfully removed directory: {directory}")
    except Exception as e:
        logger.error(f"Error cleaning directory {directory}: {str(e)}")
        raise

def fetch_dmarc_reports(imap_server, username, password, batch_size=100, days_back=30):
    """Enhanced version of the DMARC report fetcher with detailed variable debugging."""
    logger = setup_logging()
    
    # Debug print function parameters
    debug_print_var(imap_server, 'imap_server', logger)
    debug_print_var(username, 'username', logger)
    debug_print_var('*' * len(password), 'password', logger)  # Don't log actual password
    debug_print_var(batch_size, 'batch_size', logger)
    debug_print_var(days_back, 'days_back', logger)
    
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        debug_print_var(mail, 'mail', logger)
        
        mail.socket().settimeout(60)
        mail.login(username, password)
        
        status, messages = mail.select('"DMARC Reports"', readonly=True)
        debug_print_var(status, 'status', logger)
        debug_print_var(messages, 'messages', logger)
        
        if status != 'OK':
            raise Exception("Failed to select DMARC Reports folder")
        
        date = (datetime.now() - datetime.timedelta(days=days_back)).strftime("%d-%b-%Y")
        debug_print_var(date, 'date', logger)
        
        search_criteria = f'SINCE "{date}"'
        debug_print_var(search_criteria, 'search_criteria', logger)
        
        status, search_data = mail.search(None, search_criteria)
        debug_print_var(status, 'search_status', logger)
        debug_print_var(search_data, 'search_data', logger)
        
        message_ids = parse_imap_search_result(search_data)
        debug_print_var(message_ids, 'message_ids', logger)
        
        total_messages = len(message_ids)
        debug_print_var(total_messages, 'total_messages', logger)
        
        save_dir = "dmarc_reports"
        # Clean existing directory before creating new one
        clean_reports_directory(save_dir)
        os.makedirs(save_dir, exist_ok=True)
        debug_print_var(save_dir, 'save_dir', logger)
        
        processed_count = 0
        saved_count = 0
        error_count = 0
        
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i:i + batch_size]
            debug_print_var(batch, 'current_batch', logger)
            
            for msg_id in batch:
                try:
                    status, msg_data = mail.fetch(str(msg_id), '(BODY[])')
                    debug_print_var(status, f'fetch_status_msg_{msg_id}', logger)
                    debug_print_var(msg_data, f'msg_data_structure_{msg_id}', logger)
                    
                    if status != 'OK':
                        logger.error(f"Failed to fetch message {msg_id}")
                        error_count += 1
                        continue
                    
                    email_body = process_fetch_response(msg_data)
                    if not email_body:
                        logger.error(f"Could not extract email body for message {msg_id}")
                        error_count += 1
                        continue
                        
                    debug_print_var(len(email_body), 'email_body_length', logger)
                    message = email.message_from_bytes(email_body, policy=policy.default)
                    debug_print_var(message.get('subject'), f'message_subject_{msg_id}', logger)
                    
                    for part in message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        
                        filename = part.get_filename()
                        debug_print_var(filename, f'attachment_filename_{msg_id}', logger)
                        
                        if filename and any(ext in filename.lower() for ext in ['.zip', '.xml', '.gz']):
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            safe_filename = f"{timestamp}_{filename}"
                            filepath = os.path.join(save_dir, safe_filename)
                            debug_print_var(filepath, f'saving_filepath_{msg_id}', logger)
                            
                            with open(filepath, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            saved_count += 1
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing message {msg_id}: {str(e)}")
                    error_count += 1
                    continue
        
        # Debug print final counts
        debug_print_var(processed_count, 'final_processed_count', logger)
        debug_print_var(saved_count, 'final_saved_count', logger)
        debug_print_var(error_count, 'final_error_count', logger)
        
        mail.close()
        mail.logout()
        
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        raise

def parse_dmarc_report(file_path: str) -> Dict[str, Any]:
    """
    Parse DMARC report file (XML) into a structured dictionary format
    
    Args:
        file_path: Path to the report file
        
    Returns:
        Dict containing parsed report data
    """
    logging.info(f"Starting to parse DMARC report: {file_path}")
    
    # Handle XML files
    try:
        # Parse XML tree
        tree = ET.parse(file_path)
        root = tree.getroot()
        logging.debug(f"XML root tag: {root.tag}")
        
        # Initialize basic report structure
        report_data = {
            "report_metadata": {},
            "policy_published": {},
            "records": []
        }
        
        # Parse report metadata section
        metadata = root.find("report_metadata")
        if metadata is not None:
            # logging.debug("Parsing metadata section")
            report_data["report_metadata"] = {
                "org_name": getattr(metadata.find("org_name"), "text", ""),
                "email": getattr(metadata.find("email"), "text", ""),
                "report_id": getattr(metadata.find("report_id"), "text", ""),
                "date_range_begin": getattr(metadata.find("date_range/begin"), "text", ""),
                "date_range_end": getattr(metadata.find("date_range/end"), "text", "")
            }
            logging.debug(f"Metadata parsed: {report_data['report_metadata']}")
        # else:
            logging.warning("No metadata section found in XML")
        
        # Parse policy published section
        policy = root.find("policy_published")
        if policy is not None:
            # logging.debug("Parsing policy section")
            report_data["policy_published"] = {
                "domain": getattr(policy.find("domain"), "text", ""),
                "adkim": getattr(policy.find("adkim"), "text", ""),
                "aspf": getattr(policy.find("aspf"), "text", ""),
                "p": getattr(policy.find("p"), "text", ""),
                "sp": getattr(policy.find("sp"), "text", ""),
                "pct": getattr(policy.find("pct"), "text", "")
            }
            logging.debug(f"Policy parsed: {report_data['policy_published']}")
        # else:
            logging.warning("No policy section found in XML")
        
        # Parse records
        records = root.findall("record")
        logging.debug(f"Found {len(records)} records to parse")
        
        for idx, record in enumerate(records, 1):
            logging.debug(f"Parsing record {idx}/{len(records)}")
            record_data = {
                "source_ip": getattr(record.find("row/source_ip"), "text", ""),
                "count": getattr(record.find("row/count"), "text", ""),
                "policy_evaluated": {
                    "disposition": getattr(record.find("row/policy_evaluated/disposition"), "text", ""),
                    "dkim": getattr(record.find("row/policy_evaluated/dkim"), "text", ""),
                    "spf": getattr(record.find("row/policy_evaluated/spf"), "text", "")
                },
                "identifiers": {
                    "header_from": getattr(record.find("identifiers/header_from"), "text", "")
                },
                "auth_results": {
                    "dkim": getattr(record.find("auth_results/dkim/result"), "text", ""),
                    "spf": getattr(record.find("auth_results/spf/result"), "text", "")
                }
            }
            logging.debug(f"Record {idx} data: {record_data}")
            report_data["records"].append(record_data)
        
        logging.info(f"Successfully parsed XML DMARC report with {len(records)} records")
        return report_data
        
    except ET.ParseError as e:
        logging.error(f"XML parsing error in {file_path}: {str(e)}", exc_info=True)
        return {}
    except Exception as e:
        logging.error(f"Error processing XML {file_path}: {str(e)}", exc_info=True)
        return {}

def process_local_files() -> None:
    """
    Process DMARC report files from local directory with improved directory handling
    """
    logging.info(f"Starting to process local files")
    
    # Initialize DMARC analyzer
    dmarc_analyzer = DMARCAnalyzer()
    logging.debug("Initialized DMARCAnalyzer")

    try:
        # Base directory for DMARC reports
        base_path = "dmarc_reports"
        extract_dir = os.path.join(base_path, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        
        # Find all XML files recursively in extracted directories
        xml_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith(('.xml')):
                    full_path = os.path.join(root, file)
                    xml_files.append(full_path)

        if not xml_files:
            # logging.warning(f"No report files found in {extract_dir}")
            return

        total_files = len(xml_files)
        successful_count = 0

        for file_path in xml_files:
            if not os.path.isfile(file_path):
                logging.warning(f"Skipping {file_path} - not a regular file")
                continue
                
            logging.info(f"Processing file: {file_path}")
            
            try:
                report_data = parse_dmarc_report(file_path)
                if report_data:
                    logging.info("Processing parsed DMARC report")
                    process_dmarc_report(report_data, os.path.dirname(file_path), dmarc_analyzer)
                    pass
                else:
                    logging.error(f"Failed to parse DMARC report from {file_path}")
                successful_count += 1
            except Exception as e:
                logging.error(f"Error processing {file_path}: {str(e)}", exc_info=True)

        # Generate final reports
        logging.info(f"Successfully processed {successful_count}/{total_files} files")
        if successful_count > 0:
            logging.info("Saving reports")
            save_reports(base_path, dmarc_analyzer)
        else:
            logging.warning("No files were successfully processed - skipping saving reports")

    except Exception as e:
        logging.error(f"Fatal error in file processing: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    # Configuration
    IMAP_SERVER = os.getenv('IMAP_SERVER')
    USERNAME = os.getenv('IMAP_USERNAME')
    PASSWORD = os.getenv('IMAP_PASSWORD')
    
    # Debug print configuration variables
    logger = logging.getLogger(__name__)
    debug_print_var(IMAP_SERVER, 'IMAP_SERVER', logger)
    debug_print_var(USERNAME, 'USERNAME', logger)
    debug_print_var('*' * len(PASSWORD), 'PASSWORD', logger)  # Don't log actual password
    
    try:
        fetch_dmarc_reports(
            imap_server=IMAP_SERVER,
            username=USERNAME,
            password=PASSWORD,
            batch_size=100,
            days_back=7
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Script failed: {str(e)}")
        sys.exit(1)

    logging.info("=== Starting DMARC report processing ===")
    try:
        process_local_files()
        logging.info("=== File processing completed ===")
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        raise