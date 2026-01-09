import sys
try:
    from TutorDexAggregator.extractors.tutor_types import extract_tutor_types
    print('import_ok')
    print(extract_tutor_types(text='FT $40-50/hr, PT $25-30/hr'))
except Exception as e:
    print('import_error', e)
    import traceback
    traceback.print_exc()
    sys.exit(1)
