"""Verify exactly8m native reshoot and original six FLAT files; new outputs only."""
from verify_issue6_runout import main,ROOT

if __name__=='__main__':
    main(new_run=ROOT/'logs/course-native/issue6-runout8-D13550-ROLLING_UNEVEN-c2-v1',
         out=ROOT/'reports/generated/issue6-runout8',terrain_end=8.,
         report_path=ROOT/'reports/issue6-runout8-results.json')
