#!/usr/bin/env python3
"""
Phone Number Finder Script
Automatically searches for phone numbers on company websites
"""

import csv
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('phone_search.log'),
        logging.StreamHandler()
    ]
)

class PhoneNumberFinder:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Disable SSL verification for problematic sites
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # German phone number patterns - improved to match your examples
        self.phone_patterns = [
            # More flexible patterns that handle mixed hyphens and spaces
            r'\+49[\s\-]*\d{2,4}[\s\-]*\d{2,4}[\s\-]*\d{1,4}[\s\-]*\d{1,4}',  # +49-89-89 555 242
            r'\+49\s*\(\d{2,4}\)\s*\d{2,4}[\s\-]*\d{1,4}[\s\-]*\d{1,4}',     # +49(0)721-91225-35
            r'\+49\s*\d{2,4}\s*\d{2,4}\s*\d{1,4}[\s\-]*\d{1,4}',  # +49 2823 97 654 - 0
            r'0\d{2,4}[\s\-]*\d{2,4}[\s\-]*\d{1,4}[\s\-]*\d{1,4}',  # 02131-718-92-0
            r'0\d{2,4}\s*\d{2,4}\s*\d{1,4}[\s\-]*\d{1,4}',        # 02131 718 92-0
            r'0\d{2,4}[\s\-]*\d{2,4}[\s\-]*\d{1,4}',              # 07123-94723-0
            r'\+49\s*\(\d{2,4}\)\s*\d{2,4}\s*\d{1,4}',            # +49 (xxx) format
            r'\(\d{2,4}\)\s*\d{2,4}\s*\d{1,4}',                   # (xxx) format
            r'\d{2,4}\s*\/\s*\d{2,4}\s*\d{1,4}',                  # xxx/xxx format
            r'0800[\s\-]*\d{3,4}[\s\-]*\d{3,4}',                  # 0800 format
            r'\+49\s*\d{2,4}\s*\d{3,4}\s*\d{3,4}',               # +49 format (original)
            r'0\d{2,4}\s*\d{3,4}\s*\d{3,4}',                     # 0xxx format (original)
            # Additional patterns for common German formats
            r'\+49[\s\-]*\d{2,4}[\s\-]*\d{3,4}[\s\-]*\d{3,4}',    # +49-89-123-4567
            r'0\d{2,4}[\s\-]*\d{3,4}[\s\-]*\d{3,4}',             # 089-123-4567
            # Mobile numbers
            r'01[567]\d[\s\-]*\d{3,4}[\s\-]*\d{3,4}',            # 0151, 0160, 0170, 0171, etc.
        ]
        
    def clean_phone_number(self, phone):
        """Clean and validate phone number"""
        if not phone:
            return None
            
        # Remove common prefixes and clean up
        phone = re.sub(r'(tel:|telefon:|phone:|tel\.|telefon\.|phone\.)', '', phone, flags=re.IGNORECASE)
        phone = phone.strip()
        
        # Handle +49(0) format - convert to +49
        phone = re.sub(r'\+49\s*\(0\)', '+49', phone)
        
        # Remove extra whitespace
        phone = re.sub(r'\s+', ' ', phone)
        
        # Validate if it looks like a German phone number
        for pattern in self.phone_patterns:
            if re.match(pattern, phone):
                return phone
                
        return None
    
    def extract_phone_from_text(self, text):
        """Extract phone numbers from text"""
        phones = []
        
        # First, look for phone numbers with common prefixes
        prefix_patterns = [
            r'(?:fon|tel|telefon|phone|tel\.|telefon\.|phone\.)\s*[:\.]?\s*([+\d\s\-\(\)]+)',
            r'(?:Telefon|Telefonnummer|Tel\.|Fon\.)\s*[:\.]?\s*([+\d\s\-\(\)]+)',
            r'(?:Mietverwaltung|WEG-Verwaltung)\s*:\s*Tel\.\s*([+\d\s\-\(\)]+)',
        ]
        
        for pattern in prefix_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Clean up the matched phone number
                phone = re.sub(r'[^\d\s\-\(\)\+]', '', match).strip()
                if phone:
                    phones.append(phone)
        
        # Then look for standalone phone numbers using our patterns
        for pattern in self.phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        
        # Clean and validate found numbers
        valid_phones = []
        for phone in phones:
            cleaned = self.clean_phone_number(phone)
            if cleaned and cleaned not in valid_phones:
                # Prioritize phone numbers over fax numbers
                if 'fax' not in phone.lower():
                    valid_phones.append(cleaned)
        
        return valid_phones
    
    def search_contact_pages(self, base_url, soup):
        """Search for contact-related links"""
        contact_keywords = ['kontakt', 'contact', 'impressum', 'imprint', 'about', 'über']
        contact_links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            text = link.get_text().lower()
            
            for keyword in contact_keywords:
                if keyword in href or keyword in text:
                    full_url = urljoin(base_url, link['href'])
                    if full_url not in contact_links:
                        contact_links.append(full_url)
        
        return contact_links
    
    def scrape_website(self, url):
        """Scrape a website for phone numbers"""
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Try HTTPS first, then HTTP if it fails
        for protocol in ['https://', 'http://']:
            try:
                if url.startswith('https://'):
                    test_url = url
                else:
                    test_url = protocol + url.replace('https://', '').replace('http://', '')
                
                logging.info(f"Scraping: {test_url}")
                
                # Get main page
                response = self.session.get(test_url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract phone numbers from main page
                main_text = soup.get_text()
                all_phones = self.extract_phone_from_text(main_text)
                
                # If no phones found, try contact pages
                if not all_phones:
                    contact_links = self.search_contact_pages(test_url, soup)
                    
                    for contact_url in contact_links[:3]:  # Limit to first 3 contact pages
                        try:
                            logging.info(f"Trying contact page: {contact_url}")
                            contact_response = self.session.get(contact_url, timeout=10)
                            contact_response.raise_for_status()
                            
                            contact_soup = BeautifulSoup(contact_response.content, 'html.parser')
                            contact_text = contact_soup.get_text()
                            contact_phones = self.extract_phone_from_text(contact_text)
                            
                            if contact_phones:
                                all_phones.extend(contact_phones)
                                break
                                
                            time.sleep(1)  # Be respectful
                            
                        except Exception as e:
                            logging.warning(f"Error scraping contact page {contact_url}: {e}")
                            continue
                
                # Return the best phone number found
                return self.select_best_phone(all_phones) if all_phones else None
                
            except Exception as e:
                logging.warning(f"Error with {protocol}: {e}")
                if protocol == 'https://':
                    continue  # Try HTTP next
                else:
                    logging.error(f"Error scraping {url}: {e}")
                    return None
        
        return None
    
    def select_best_phone(self, phones):
        """Select the best phone number from a list based on priority"""
        if not phones:
            return None
        
        # Remove duplicates and clean
        unique_phones = list(set(phones))
        
        # Priority order: main office numbers first, then mobile, then others
        priority_keywords = [
            'haupt', 'zentrale', 'büro', 'office', 'kontakt', 'info',
            'verwaltung', 'administration', 'service'
        ]
        
        # Check if any phone has priority keywords in context
        for phone in unique_phones:
            # For now, prioritize non-mobile numbers
            if not phone.startswith('01'):
                return phone
        
        # If no clear priority, return the first one
        return unique_phones[0]
    
    def process_csv(self, input_file, output_file):
        """Process the CSV file and find phone numbers"""
        results = []
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total_rows = sum(1 for row in reader)
            f.seek(0)  # Reset file pointer
            next(reader)  # Skip header again
            
            for i, row in enumerate(reader, 1):
                company_name = row.get('company_name', '').strip()
                website = row.get('website', '').strip()
                
                if not company_name or not website:
                    continue
                
                # Search for phone number
                phone = self.scrape_website(website)
                
                if phone:
                    results.append([company_name, website, phone])
                    logging.info(f"[{i}/{total_rows}] {company_name}: Found phone {phone}")
                else:
                    results.append([company_name, website, ''])
                    logging.info(f"[{i}/{total_rows}] {company_name}: No phone found")
                
                # Be respectful with delays
                time.sleep(2)
                
                # Save progress every 20 companies (more frequent for smaller dataset)
                if i % 20 == 0:
                    self.save_results(results, output_file)
                    logging.info(f"Progress saved: {i}/{total_rows} companies processed")
        
        # Final save
        self.save_results(results, output_file)
        logging.info(f"Completed! Processed {len(results)} companies")
        
        # Summary
        found_phones = sum(1 for r in results if r[2])
        logging.info(f"Phone numbers found: {found_phones}/{len(results)}")
    
    def save_results(self, results, output_file):
        """Save results to CSV"""
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['company_name', 'website', 'phone'])
            writer.writerows(results)

def main():
    finder = PhoneNumberFinder()
    
    input_file = 'docs/companies.csv'
    output_file = 'docs/phone_collection.csv'
    
    print("Starting improved phone number search...")
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print("This may take a while. Progress will be saved every 20 companies.")
    print("Press Ctrl+C to stop at any time.")
    
    try:
        finder.process_csv(input_file, output_file)
        print(f"\nCompleted! Results saved to {output_file}")
        
        # Show summary
        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total = 0
            found = 0
            for row in reader:
                total += 1
                if row['phone'].strip():
                    found += 1
        
        print(f"\nSummary:")
        print(f"Total companies processed: {total}")
        print(f"Phone numbers found: {found}")
        print(f"Success rate: {(found/total*100):.1f}%")
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
        print("Partial results have been saved")

if __name__ == "__main__":
    main() 