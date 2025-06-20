"""
Concrete factory implementation for creating platform-specific scrapers and parsers.

This module provides the ConcreteScraperFactory class that implements the ScraperFactory
interface for dynamically discovering, loading, and instantiating platform-specific
scraper and parser components.

The factory automatically discovers available platforms in the platforms/ directory
and provides a unified interface for creating platform-specific instances with
proper configuration loading and validation.
"""

import os
import importlib
import inspect
from typing import Dict, Any, List, Type, Optional
from pathlib import Path

from .common.base import ScraperFactory, Scraper, Parser
from .common.logging import setup_scraper_logger
from .common.config import JOB_DETAIL_CONCURRENCY

logger = setup_scraper_logger()


class ConcreteScraperFactory(ScraperFactory):
    """
    Concrete implementation of the ScraperFactory interface.
    
    This factory provides automatic platform discovery, dynamic module loading,
    and creation of platform-specific scraper and parser instances with proper
    configuration management and validation.
    """
    
    def __init__(self):
        """Initialize the factory and discover available platforms."""
        self._platforms: Dict[str, Dict[str, Any]] = {}
        self._discover_platforms()
    
    def _discover_platforms(self) -> None:
        """
        Automatically discover available platforms in the platforms/ directory.
        
        Scans the platforms directory for subdirectories containing platform
        implementations and registers them for dynamic loading.
        """
        platforms_dir = Path(__file__).parent / "platforms"
        
        if not platforms_dir.exists():
            logger.warning(f"Platforms directory not found: {platforms_dir}")
            return
        
        logger.info(f"Discovering platforms in: {platforms_dir}")
        
        for platform_path in platforms_dir.iterdir():
            if platform_path.is_dir() and not platform_path.name.startswith('_'):
                platform_name = platform_path.name.lower()
                
                # Check if platform has required modules
                required_modules = ['crawler', 'parser', 'config']
                platform_modules = {}
                
                for module_name in required_modules:
                    module_file = platform_path / f"{module_name}.py"
                    if module_file.exists():
                        platform_modules[module_name] = True
                    else:
                        logger.warning(f"Platform '{platform_name}' missing {module_name}.py")
                        platform_modules[module_name] = False
                
                # Register platform if it has all required modules
                if all(platform_modules.values()):
                    self._platforms[platform_name] = {
                        'path': platform_path,
                        'modules': platform_modules
                    }
                    logger.info(f"Registered platform: {platform_name}")
                else:
                    logger.warning(f"Skipping incomplete platform: {platform_name}")
    
    def _load_platform_module(self, platform: str, module_name: str) -> Any:
        """
        Dynamically load a platform-specific module.
        
        Args:
            platform: Platform identifier (e.g., "workday")
            module_name: Module name to load (e.g., "crawler", "parser", "config")
            
        Returns:
            Loaded module object
            
        Raises:
            ImportError: If the module cannot be imported
            ValueError: If the platform is not supported
        """
        if platform not in self._platforms:
            raise ValueError(f"Unsupported platform: {platform}")
        
        module_path = f"role_aggr.scraper.platforms.{platform}.{module_name}"
        
        try:
            module = importlib.import_module(module_path)
            logger.debug(f"Successfully loaded module: {module_path}")
            return module
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            raise ImportError(f"Cannot import {module_name} for platform {platform}: {e}")
    
    def _load_platform_config(self, platform: str) -> Dict[str, Any]:
        """
        Load platform-specific configuration with fallback to general config.
        
        Args:
            platform: Platform identifier
            
        Returns:
            Configuration dictionary containing platform-specific settings
        """
        config = {}
        
        try:
            # Load platform-specific config
            config_module = self._load_platform_module(platform, 'config')
            
            # Extract all uppercase attributes as config values
            for attr_name in dir(config_module):
                if attr_name.isupper() and not attr_name.startswith('_'):
                    config[attr_name.lower()] = getattr(config_module, attr_name)
            
            logger.debug(f"Loaded platform config for {platform}: {list(config.keys())}")
            
        except ImportError:
            logger.warning(f"No platform-specific config found for {platform}")
        
        # Add general config values with fallback
        if 'job_detail_concurrency' not in config:
            config['job_detail_concurrency'] = JOB_DETAIL_CONCURRENCY
        
        return config
    
    def _find_class_in_module(self, module: Any, base_class: Type, platform: str) -> Type:
        """
        Find a class in a module that implements the specified base class.
        
        Args:
            module: Module to search in
            base_class: Base class that the target class should implement
            platform: Platform name for error messages
            
        Returns:
            Class that implements the base class
            
        Raises:
            ValueError: If no suitable class is found or validation fails
        """
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip the base class itself and imported classes
            if (obj != base_class and 
                issubclass(obj, base_class) and 
                obj.__module__ == module.__name__):
                
                logger.debug(f"Found {base_class.__name__} implementation: {name}")
                return obj
        
        raise ValueError(f"No {base_class.__name__} implementation found in {platform} module")
    
    def _validate_class_implementation(self, cls: Type, base_class: Type, platform: str) -> None:
        """
        Validate that a class properly implements the required abstract methods.
        
        Args:
            cls: Class to validate
            base_class: Base class with abstract methods
            platform: Platform name for error messages
            
        Raises:
            ValueError: If the class doesn't implement required methods
        """
        # Check if class can be instantiated (no abstract methods remaining)
        try:
            if base_class == Scraper:
                # For Scraper, we need a config parameter
                test_config = {'test': True}
                instance = cls(test_config)
            else:
                # For Parser, no parameters needed
                instance = cls()
            
            # If we get here, the class is properly implemented
            logger.debug(f"Validated {base_class.__name__} implementation for {platform}")
            
        except TypeError as e:
            if "abstract methods" in str(e):
                raise ValueError(f"{cls.__name__} for platform {platform} has unimplemented abstract methods: {e}")
            else:
                raise ValueError(f"Failed to instantiate {cls.__name__} for platform {platform}: {e}")
    
    def create_scraper(self, platform: str, config: Dict[str, Any]) -> Scraper:
        """
        Create a platform-specific scraper instance.
        
        Args:
            platform: Platform identifier (e.g., "workday")
            config: Platform-specific configuration dictionary
            
        Returns:
            Configured scraper instance for the specified platform
            
        Raises:
            ValueError: If the platform is not supported or configuration is invalid
            ImportError: If the platform module cannot be imported
        """
        platform = platform.lower()
        
        logger.info(f"Creating scraper for platform: {platform}")
        
        try:
            # Load platform configuration and merge with provided config
            platform_config = self._load_platform_config(platform)
            # Merge provided config with platform config (provided config takes precedence)
            merged_config = {**platform_config, **config}
            merged_config['platform'] = platform
            
            # Load the crawler module (contains Scraper implementation)
            crawler_module = self._load_platform_module(platform, 'crawler')
            
            # Find the Scraper implementation
            scraper_class = self._find_class_in_module(crawler_module, Scraper, platform)
            
            # Validate the implementation
            self._validate_class_implementation(scraper_class, Scraper, platform)
            
            # Create and return the scraper instance
            scraper_instance = scraper_class(merged_config)
            logger.info(f"Successfully created {scraper_class.__name__} for {platform}")
            
            return scraper_instance
            
        except Exception as e:
            logger.error(f"Failed to create scraper for platform {platform}: {e}")
            raise
    
    def create_parser(self, platform: str) -> Parser:
        """
        Create a platform-specific parser instance.
        
        Args:
            platform: Platform identifier (e.g., "workday")
            
        Returns:
            Parser instance for the specified platform
            
        Raises:
            ValueError: If the platform is not supported
            ImportError: If the platform module cannot be imported
        """
        platform = platform.lower()
        
        logger.info(f"Creating parser for platform: {platform}")
        
        try:
            # Load the parser module
            parser_module = self._load_platform_module(platform, 'parser')
            
            # Find the Parser implementation
            parser_class = self._find_class_in_module(parser_module, Parser, platform)
            
            # Validate the implementation
            self._validate_class_implementation(parser_class, Parser, platform)
            
            # Create and return the parser instance
            parser_instance = parser_class()
            logger.info(f"Successfully created {parser_class.__name__} for {platform}")
            
            return parser_instance
            
        except Exception as e:
            logger.error(f"Failed to create parser for platform {platform}: {e}")
            raise
    
    def get_supported_platforms(self) -> List[str]:
        """
        Get a list of all supported platforms.
        
        Returns:
            List of platform identifiers that can be used with this factory
        """
        return list(self._platforms.keys())
    
    def is_platform_supported(self, platform: str) -> bool:
        """
        Check if a platform is supported by this factory.
        
        Args:
            platform: Platform identifier to check
            
        Returns:
            True if the platform is supported, False otherwise
        """
        return platform.lower() in self._platforms