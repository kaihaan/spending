/**
 * AutocompleteCombobox Component
 *
 * A searchable combobox that allows typing to filter options and selecting from a dropdown.
 * Supports custom option rendering and creating new entries.
 */

import { useState, useRef, useEffect, useCallback } from 'react';

export interface ComboboxOption {
  value: string;
  label: string;
  sublabel?: string;
}

interface AutocompleteComboboxProps {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  allowCreate?: boolean;
  createLabel?: string;
  disabled?: boolean;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
}

export default function AutocompleteCombobox({
  options,
  value,
  onChange,
  placeholder = 'Search...',
  label,
  allowCreate = false,
  createLabel = 'Create',
  disabled = false,
  className = '',
  size = 'sm',
}: AutocompleteComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync input value with prop value
  useEffect(() => {
    const selectedOption = options.find((opt) => opt.value === value);
    setInputValue(selectedOption?.label || value);
  }, [value, options]);

  // Filter options based on input
  const filteredOptions = options.filter((opt) =>
    opt.label.toLowerCase().includes(inputValue.toLowerCase())
  );

  // Check if we should show "create new" option
  const showCreateOption =
    allowCreate &&
    inputValue.trim() &&
    !options.some((opt) => opt.label.toLowerCase() === inputValue.toLowerCase());

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        // Reset input to selected value on blur
        const selectedOption = options.find((opt) => opt.value === value);
        setInputValue(selectedOption?.label || value);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [value, options]);

  // Scroll highlighted option into view
  useEffect(() => {
    if (highlightedIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightedIndex] as HTMLElement;
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightedIndex]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
    setIsOpen(true);
    setHighlightedIndex(-1);
  };

  const handleSelect = useCallback(
    (optionValue: string, optionLabel?: string) => {
      onChange(optionValue);
      setInputValue(optionLabel || optionValue);
      setIsOpen(false);
      setHighlightedIndex(-1);
    },
    [onChange]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const totalOptions = filteredOptions.length + (showCreateOption ? 1 : 0);

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setIsOpen(true);
        setHighlightedIndex((prev) => (prev < totalOptions - 1 ? prev + 1 : prev));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : prev));
        break;
      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0) {
          if (highlightedIndex < filteredOptions.length) {
            const opt = filteredOptions[highlightedIndex];
            handleSelect(opt.value, opt.label);
          } else if (showCreateOption) {
            handleSelect(inputValue.trim(), inputValue.trim());
          }
        } else if (showCreateOption) {
          handleSelect(inputValue.trim(), inputValue.trim());
        }
        break;
      case 'Escape':
        setIsOpen(false);
        const selectedOption = options.find((opt) => opt.value === value);
        setInputValue(selectedOption?.label || value);
        break;
      case 'Tab':
        setIsOpen(false);
        break;
    }
  };

  const sizeClasses = {
    xs: 'input-xs text-xs',
    sm: 'input-sm text-sm',
    md: '',
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {label && (
        <label className="label py-1">
          <span className="label-text text-sm">{label}</span>
        </label>
      )}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          className={`input input-bordered w-full ${sizeClasses[size]}`}
          value={inputValue}
          onChange={handleInputChange}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
        />
        <button
          type="button"
          className="absolute inset-y-0 right-0 flex items-center px-2 text-base-content/50"
          onClick={() => {
            setIsOpen(!isOpen);
            inputRef.current?.focus();
          }}
          disabled={disabled}
          tabIndex={-1}
        >
          <svg
            className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {isOpen && (filteredOptions.length > 0 || showCreateOption) && (
        <ul
          ref={listRef}
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-base-300 bg-base-100 py-1 shadow-lg"
        >
          {filteredOptions.map((option, index) => (
            <li
              key={option.value}
              className={`cursor-pointer px-3 py-2 ${
                highlightedIndex === index ? 'bg-primary text-primary-content' : 'hover:bg-base-200'
              } ${option.value === value ? 'font-semibold' : ''}`}
              onClick={() => handleSelect(option.value, option.label)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              <div className="text-sm">{option.label}</div>
              {option.sublabel && (
                <div
                  className={`text-xs ${
                    highlightedIndex === index ? 'text-primary-content/70' : 'text-base-content/50'
                  }`}
                >
                  {option.sublabel}
                </div>
              )}
            </li>
          ))}
          {showCreateOption && (
            <li
              className={`cursor-pointer px-3 py-2 border-t border-base-200 ${
                highlightedIndex === filteredOptions.length
                  ? 'bg-primary text-primary-content'
                  : 'hover:bg-base-200'
              }`}
              onClick={() => handleSelect(inputValue.trim(), inputValue.trim())}
              onMouseEnter={() => setHighlightedIndex(filteredOptions.length)}
            >
              <div className="flex items-center gap-2 text-sm">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                {createLabel} "{inputValue.trim()}"
              </div>
            </li>
          )}
        </ul>
      )}

      {isOpen && filteredOptions.length === 0 && !showCreateOption && inputValue && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-base-300 bg-base-100 px-3 py-2 text-sm text-base-content/50 shadow-lg">
          No matches found
        </div>
      )}
    </div>
  );
}
