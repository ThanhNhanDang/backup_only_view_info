# -*- coding: utf-8 -*-
import requests
import os
import time
from datetime import datetime
import pytz

class OdooBackupManager:
    def __init__(self, odoo_url, master_password, local_tz):
        self.odoo_url = odoo_url.rstrip('/')
        self.master_password = master_password
        self.local_tz = local_tz
        
    def backup_database(self, db_name, backup_format='zip'):
        """
        Backup database using Odoo's web/database/backup endpoint
        
        Args:
            db_name: Database name to backup
            backup_format: 'zip' (with filestore) or 'dump' (database only)
            
        Returns:
            tuple: (success: bool, file_path: str or error_message: str)
        """
        url = f"{self.odoo_url}/web/database/backup"
        
        payload = {
            'master_pwd': self.master_password,
            'name': db_name,
            'backup_format': backup_format
        }
        
        try:
            print(f"[INFO] Starting backup for database: {db_name}")
            response = requests.post(url, data=payload, stream=True, timeout=3600)
            
            if response.status_code == 200:
                # Generate filename with timestamp
                now = datetime.now(self.local_tz).strftime("%Y-%m-%d_%H-%M-%S")
                extension = 'zip' if backup_format == 'zip' else 'dump'
                filename = f"{db_name}_{now}.{extension}"
                
                return True, filename, response.content
            else:
                error_msg = f"Backup failed with status code: {response.status_code}"
                print(f"[ERROR] {error_msg}")
                return False, error_msg, None
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg, None
    
    def restore_database(self, backup_file_path, db_name=None, copy=False):
        """
        Restore database using Odoo's web/database/restore endpoint
        
        Args:
            backup_file_path: Path to backup file (.zip or .dump)
            db_name: Name for restored database (if None, use original name)
            copy: If True, don't delete existing database
            
        Returns:
            tuple: (success: bool, message: str)
        """
        url = f"{self.odoo_url}/web/database/restore"
        
        if not os.path.exists(backup_file_path):
            return False, f"Backup file not found: {backup_file_path}"
        
        # If db_name not provided, extract from filename
        if not db_name:
            db_name = os.path.basename(backup_file_path).split('_')[0]
        
        try:
            print(f"[INFO] Starting restore from: {backup_file_path}")
            
            with open(backup_file_path, 'rb') as backup_file:
                files = {
                    'backup_file': (os.path.basename(backup_file_path), backup_file, 'application/octet-stream')
                }
                
                data = {
                    'master_pwd': self.master_password,
                    'name': db_name,
                    'copy': str(copy).lower()
                }
                
                response = requests.post(url, data=data, files=files, timeout=3600)
                
                if response.status_code == 200:
                    print(f"[INFO] Database restored successfully: {db_name}")
                    return True, f"Database '{db_name}' restored successfully"
                else:
                    error_msg = f"Restore failed with status code: {response.status_code}"
                    try:
                        error_detail = response.json()
                        error_msg += f" - {error_detail}"
                    except:
                        error_msg += f" - {response.text[:200]}"
                    print(f"[ERROR] {error_msg}")
                    return False, error_msg
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg
    
    def drop_database(self, db_name):
        """
        Drop database using Odoo's web/database/drop endpoint
        
        Args:
            db_name: Database name to drop
            
        Returns:
            tuple: (success: bool, message: str)
        """
        url = f"{self.odoo_url}/web/database/drop"
        
        payload = {
            'master_pwd': self.master_password,
            'name': db_name
        }
        
        try:
            print(f"[INFO] Dropping database: {db_name}")
            response = requests.post(url, data=payload)
            
            if response.status_code == 200:
                print(f"[INFO] Database dropped successfully: {db_name}")
                return True, f"Database '{db_name}' dropped successfully"
            else:
                error_msg = f"Drop failed with status code: {response.status_code}"
                print(f"[ERROR] {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg
    
    def duplicate_database(self, source_db, target_db):
        """
        Duplicate database using Odoo's web/database/duplicate endpoint
        
        Args:
            source_db: Source database name
            target_db: Target database name
            
        Returns:
            tuple: (success: bool, message: str)
        """
        url = f"{self.odoo_url}/web/database/duplicate"
        
        payload = {
            'master_pwd': self.master_password,
            'name': source_db,
            'new_name': target_db
        }
        
        try:
            print(f"[INFO] Duplicating database: {source_db} -> {target_db}")
            response = requests.post(url, data=payload, timeout=3600)
            
            if response.status_code == 200:
                print(f"[INFO] Database duplicated successfully")
                return True, f"Database duplicated: {source_db} -> {target_db}"
            else:
                error_msg = f"Duplicate failed with status code: {response.status_code}"
                print(f"[ERROR] {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg