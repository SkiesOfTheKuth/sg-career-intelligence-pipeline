"""Fixed claim/ranking review corpus for documented-fit-v2."""
import json
import unittest
from pathlib import Path
from evidence import build_job, extract_requirements, draft_templates
from fit_score import requirement, language_gaps, _duty


class FitV2Tests(unittest.TestCase):
    def test_preferred_industry_does_not_waive_required_experience(self):
        for wording in (
            '3+ years of experience in social media account management and content creation, preferably in an agency environment',
            'At least 5 years of marketing experience, ideally within hospitality',
        ):
            job = build_job({'title': 'Marketing Executive', 'description':
                'Responsibilities\nManage social media accounts.\nRequirements\n' + wording}, 'optional-scope')
            self.assertTrue(any(gate['kind'] == 'experience' for gate in job['assessment']['score']['gates']), wording)
            self.assertLessEqual(job['assessment']['score']['value'], 39)
            self.assertTrue(job['requirements']['preferred'])
        for wording in ('3 years of marketing experience preferred', 'Preferably 3 years of marketing experience'):
            job = build_job({'title': 'Marketing Executive', 'description':
                'Responsibilities\nManage social media accounts.\nRequirements\n' + wording}, 'optional-duration')
            self.assertFalse(job['assessment']['score']['gates'])
            self.assertEqual(job['requirements']['mandatory'], [])

    def test_retained_candidate_headings_are_not_requirements(self):
        rows = json.loads(Path(__file__).with_name('fit_review_real_sources.json').read_text(encoding='utf-8'))
        raw = next(row for row in rows if row['legacy_id'] == 'SG-OPP-0111')
        job = build_job(raw, raw['legacy_id'])
        score = job['assessment']['score']
        self.assertTrue(any(gate['kind'] == 'experience' for gate in score['gates']))
        self.assertFalse(any('not clearly separate responsibilities' in limit['reason'] for limit in score['limits']))
        for heading in ("Skills & Experience We're Looking For", 'What Sets You Apart'):
            self.assertNotIn(heading, job['requirements']['mandatory'])
            self.assertNotIn(heading, job['requirements']['preferred'])
        self.assertIn('Background in influencer marketing campaigns', job['requirements']['preferred'])

    def test_alternative_candidate_headings_do_not_add_unknown_duties(self):
        for original, alternative in [('Requirements', "Skills & Experience We're Looking For"),
                                      ('Preferred qualifications', 'What Sets You Apart')]:
            scores = [build_job({'title': 'Marketing Executive', 'description':
                'Responsibilities\nManage social media accounts.\n' + heading + '\nDegree in Marketing'}, heading)['assessment']['score']
                for heading in (original, alternative)]
            self.assertEqual(scores[0]['duties'], scores[1]['duties'])
            self.assertEqual(scores[0]['value'], scores[1]['value'])

    def test_combined_supported_domains_do_not_repeat_existing_credit(self):
        description = 'Responsibilities\nManage social media accounts.\nCreate social media content.\nEdit video.\nRequirements\nDegree in Marketing'
        original = build_job({'title': 'Marketing Executive', 'description': description}, 'base')
        repeated = build_job({'title': 'Marketing Executive', 'description': description.replace(
            'Edit video.', 'Schedule social media content.\nEdit video.')}, 'repeated')
        self.assertEqual(original['assessment']['score']['components'][1], repeated['assessment']['score']['components'][1])

    def test_plural_email_channels_and_nonsocial_content_stay_unproven(self):
        for quote in (
            'Develop marketing content for social media, EDMs, event collaterals and presentations.',
            'Plan, create and adapt content for social media, eDMs, and other digital channels.',
            'Manage social media platforms, job portals and online marketing channels.',
            'Develop lead-generation content such as e-books, reports and short courses.',
        ):
            row = _duty(quote)
            self.assertFalse(row['candidate_evidence'], quote)
            self.assertEqual(row['quote'], quote)
        self.assertTrue(_duty('Create content for social media.')['candidate_evidence'])

    def test_degree_alternative_does_not_prove_additional_skill(self):
        quote = 'Minimum Diploma or Degree in Communications/Marketing, working knowledge in Graphic Design or other related fields'
        self.assertNotEqual(requirement(quote)['status'], 'supported')
        job = build_job({'title': 'Marketing Executive', 'description':
            'Responsibilities\nManage social media.\nRequirements\n' + quote}, 'degree-skill')
        rows = job['assessment']['score']['requirements']
        self.assertTrue(any(row['status'] == 'supported' and 'Degree' in row['quote'] for row in rows))
        self.assertTrue(any(row['status'] == 'check' and 'Graphic Design' in row['quote'] for row in rows))
        self.assertTrue(all(row['quote'] in quote for row in rows))

    def test_unheaded_gerund_duties_are_retained_in_denominator(self):
        duties = ['Managing social media accounts and website content and enquiries.',
                  'Answering enquiries via emails and social media platforms.',
                  'Creating content by working closely with other departments and partners.',
                  'Managing communications volunteers.', 'Perform ad-hoc duties as assigned.']
        job = build_job({'title': 'Marketing Executive', 'description':
            '\n'.join(duties) + '\nRequirements\nDegree in Marketing'}, 'gerunds')
        rows = job['assessment']['score']['duties']
        self.assertEqual([row['quote'] for row in rows], duties)
        self.assertFalse(rows[0]['candidate_evidence'])
        self.assertFalse(rows[1]['candidate_evidence'])
        self.assertTrue(rows[2]['candidate_evidence'])

    def test_comma_actions_separate_leadership_from_research(self):
        quote = 'Lead the marketing team, conduct market research'
        row = _duty(quote)
        self.assertEqual(row['status'], 'partial')
        self.assertFalse(row['clauses'][0]['candidate_evidence'])
        self.assertTrue(row['clauses'][1]['candidate_evidence'])
        self.assertTrue(all(clause['source_quote'] == quote for clause in row['clauses']))
        # Coordinated verbs with one shared object must not create empty duties.
        self.assertEqual(len(_duty('Create, curate, and schedule content aligned with brand voice.')['clauses']), 1)

    def test_content_object_does_not_establish_interview_method(self):
        self.assertFalse(_duty('Conduct interviews with members and staff to create engaging content.')['candidate_evidence'])

    def test_campaign_metrics_do_not_establish_spend_optimisation(self):
        self.assertFalse(_duty('Track, analyze, and report on campaign performance metrics and ROI to optimize marketing spend.')['candidate_evidence'])

    def test_real_content_scope_does_not_expand_cv_channels_or_visual_skills(self):
        for quote in ('Plan and implement multi-channel content strategy (social, email, digital).',
                      'Assist in developing engaging visual and written content aligned with brand guidelines',
                      'Maintain and organize digital assets including visuals, captions, and content calendars'):
            row = _duty(quote)
            self.assertFalse(row['candidate_evidence'], quote)

    def test_concatenated_source_duties_cannot_share_credit_across_sentences(self):
        quote = ('Digital Marketing & Social MediaCreate on-brand content across social media and eDM platforms.'
                 'Manage digital channels, including website updates and social media platforms.'
                 'Monitor and optimise campaigns using data analytics to ensure audience reach and engagement.')
        row = _duty(quote)
        self.assertGreaterEqual(len(row['clauses']), 3)
        for clause in row['clauses']:
            self.assertEqual(clause['source_quote'], quote)
            if 'eDM' in clause['quote'] or 'website' in clause['quote']:
                self.assertFalse(clause['candidate_evidence'])
        self.assertFalse(any(clause['quote'] == 'engagement.' for clause in row['clauses']))

    def test_community_responses_are_not_analytics(self):
        row = _duty('Monitor comments, messages, and community engagement; respond in a timely and professional manner')
        self.assertNotIn('analytics', row['domains'])
        self.assertIn('social', row['domains'])

    def test_mixed_optional_language_cannot_waive_mandatory_language(self):
        for wording in ('Japanese required; Thai preferred.', 'Japanese not required, but Mandarin required.', 'Fluent Japanese required and Thai preferred.', 'Japanese not required, Mandarin required.'):
            job = build_job({'title':'Marketing Executive', 'description':'Responsibilities\nManage social media accounts.\nRequirements\n'+wording}, 'language')
            self.assertTrue(job['assessment']['score']['gates'], wording)
            self.assertLessEqual(job['assessment']['score']['value'], 39)
        self.assertFalse(language_gaps(['Japanese is not required.']))
        job = build_job({'title':'Marketing', 'description':'Thai language is not required.'}, 'thai')
        self.assertIsNone(job['thai_relevance'])
        explicit = build_job({'title':'Marketing', 'requirements':{'mandatory':['Thai language required']}}, 'explicit-thai')
        self.assertEqual(explicit['thai_relevance'], 'Thai required')

    def test_social_channel_does_not_establish_customer_case_management(self):
        row = _duty('Manage and document customer cases from initial social media contact through resolution.')
        self.assertFalse(row['candidate_evidence'])

    def test_negated_duties_and_named_tools_do_not_claim_support(self):
        for wording in ('Do not manage social media accounts.', 'Do not create content and manage social media accounts.', 'Manage social media accounts using Hootsuite.', 'Manage social media accounts using Sprout Social.', 'Manage social media accounts using UnverifiedTool.'):
            self.assertFalse(_duty(wording)['candidate_evidence'], wording)

    def test_cv_influencer_product_launch_scope_is_supported(self):
        self.assertEqual(_duty('Coordinate influencer outreach and contracts for product launches.')['status'], 'overlap')

    def test_compound_actions_keep_shared_object_and_partial_scopes(self):
        self.assertEqual(_duty('Plan and manage social media accounts.')['status'], 'overlap')
        row = _duty('Manage social media accounts and paid advertising budgets.')
        self.assertEqual(row['status'], 'partial')
        self.assertEqual(len(row['clauses']), 2)
        self.assertFalse(row['clauses'][1]['candidate_evidence'])
        quote = 'Manage social media accounts; create graphics and animation.'
        job = build_job({'title':'Marketing', 'description':'Responsibilities\n'+quote+'\nRequirements\nDegree in Marketing'}, 'semicolon')
        row = job['assessment']['score']['duties'][0]
        self.assertEqual(row['quote'], quote)
        self.assertTrue(all(part['source_quote'] == quote for part in row['clauses']))

    def test_recruiter_voice_does_not_hide_candidate_requirements(self):
        req = extract_requirements('Requirements\nWe are looking for fluent Japanese speakers.\nDegree in Marketing')
        self.assertIn('We are looking for fluent Japanese speakers.', req['mandatory'])
        self.assertIn('Degree in Marketing', req['mandatory'])

    def test_mixed_degree_conjunction_needs_review(self):
        self.assertNotEqual(requirement('Degree in Marketing or Communications and Law')['status'], 'supported')

    @classmethod
    def setUpClass(cls):
        cls.jobs = {r['id']: build_job(r, r['id']) for r in json.loads(Path(__file__).with_name('fit_review_corpus.json').read_text(encoding='utf-8'))}

    def test_graphics_topic_is_not_social_management(self):
        score = self.jobs['graphics']['assessment']['score']
        self.assertEqual(score['version'], 'documented-fit-v2')
        self.assertEqual(score['components'][1]['earned'], 0)
        self.assertFalse(any(r['candidate_evidence'] for r in score['duties']))

    def test_compound_duty_is_partial_and_preserves_quote(self):
        row = self.jobs['compound']['assessment']['score']['duties'][0]
        self.assertEqual(row['status'], 'partial')
        self.assertEqual(row['quote'], 'Manage social media accounts and create graphics and animation.')
        self.assertTrue(any(c['status'] == 'overlap' for c in row['clauses']))
        self.assertTrue(any(c['status'] == 'check' for c in row['clauses']))
        self.assertGreater(self.jobs['aligned']['assessment']['score']['value'], self.jobs['compound']['assessment']['score']['value'])

    def test_degree_alternatives_and_unicode_bullets(self):
        for line in ['• Bachelor’s degree in Graphic Design, Communications or Marketing.', 'Degree in Computer Science / Marketing']:
            self.assertEqual(requirement(line)['status'], 'supported', line)
        self.assertNotEqual(requirement('Degree in Graphic Design')['status'], 'supported')
        self.assertNotEqual(requirement('Degree in Communications')['status'], 'supported')
        self.assertEqual(requirement('Degree in Communications or Marketing')['status'], 'supported')

    def test_boilerplate_is_not_candidate_requirement(self):
        req = extract_requirements('Requirements\nDegree in Marketing\nOur company has 30 years of experience.\nEA Licence No: 12C3456\nPlease apply with your CV.\nReg No R1234567')
        self.assertEqual(req['mandatory'], ['Degree in Marketing'])

    def test_corpus_gates_and_ranking(self):
        scores = {key: job['assessment']['score'] for key, job in self.jobs.items()}
        self.assertGreater(scores['aligned']['value'], scores['adjacent']['value'])
        self.assertLessEqual(scores['japanese']['value'], 39)
        self.assertLessEqual(scores['finance']['value'], 39)
        self.assertIsNone(scores['incomplete']['value'])
        self.assertNotEqual(self.jobs['propertyguru']['thai_relevance'], 'Thai required')
        self.assertEqual(scores['japanese']['gates'][0]['evidence_state'], 'missing_candidate_evidence')
        self.assertEqual(scores['incomplete']['evidence_state'], 'missing_source')

    def test_drafts_use_relevant_pairs_and_separate_checks(self):
        draft = draft_templates(self.jobs['interpretation'])
        self.assertIn('Thai–English', draft['cover_letter'])
        self.assertNotIn('influencer', draft['cover_letter'])
        self.assertIn('Requirements to check', draft['interview_prep'])
        self.assertNotIn('Requirements to check', draft['cover_letter'])
        self.assertIsInstance(draft['requirements_to_check'], list)
        self.assertTrue(draft['supported_pairs'])

    def test_employment_types_are_memberships(self):
        job = build_job({'title':'Marketing','employment_type':'Full Time, Freelance','source':'MyCareersFuture'}, 'types')
        self.assertEqual(job['employment_types'], ['Full-time', 'Freelance'])

    def test_scope_prevents_topic_only_support(self):
        for duty in ['Monitor and report on revenue performance metrics.', 'Explore AI tools to enhance content creation.', 'Capture and edit photos to create social media content.', 'Develop software to monitor social media accounts.', 'Conduct research into social media management software.', 'Design marketing proposals in Adobe Illustrator.', 'Develop algorithms for content creation.', 'Buy content creation services.', 'Translate marketing proposals into Japanese.']:
            job = build_job({'title':'Marketing Executive','description':'Responsibilities\n' + duty + '\nRequirements\nDegree in Marketing'}, 'scope')
            self.assertFalse(any(row['candidate_evidence'] for row in job['assessment']['score']['duties']), duty)

    def test_documented_incompatibility_is_distinct_from_missing_evidence(self):
        self.assertEqual(requirement('Singapore citizens only')['evidence_state'], 'documented_incompatibility')
        self.assertEqual(requirement('Fluent Japanese')['evidence_state'], 'missing_candidate_evidence')

    def test_retained_top_recommendations_do_not_award_specialist_scope(self):
        rows = json.loads(Path(__file__).with_name('fit_review_real_sources.json').read_text(encoding='utf-8'))
        jobs = {row['legacy_id']: build_job(row, row['legacy_id']) for row in rows}
        revenue = jobs['SG-OPP-2437']
        self.assertFalse(any('opened for business' in line for line in revenue['requirements']['mandatory']))
        self.assertFalse(any('clientele' in line for line in revenue['requirements']['mandatory']))
        for job in jobs.values():
            self.assertFalse(any('Disclaimer:' == line or 'Why Join Us?' == line for line in job['requirements']['mandatory']))
            for duty in job['assessment']['score']['duties']:
                for clause in duty['clauses']:
                    if any(term in clause['quote'].lower() for term in ['revenue performance', 'edit photos', 'adobe', 'graphic design', 'video production', 'media invites', 'customer cases', 'edms', 'job portals', 'e-books', 'lead the marketing team', 'conduct interviews', 'marketing spend']):
                        self.assertEqual(clause['candidate_evidence'], [], clause['quote'])
                    if clause['candidate_evidence']:
                        self.assertEqual(clause['status'], 'overlap')
                        self.assertEqual(clause['source_quote'], duty['quote'])
        self.assertGreater(jobs['SG-OPP-2507']['assessment']['score']['value'], revenue['assessment']['score']['value'])
        self.assertGreater(jobs['SG-OPP-2507']['assessment']['score']['value'], jobs['SG-OPP-2842']['assessment']['score']['value'])
        self.assertGreater(jobs['SG-OPP-2507']['assessment']['score']['value'], jobs['SG-OPP-0124']['assessment']['score']['value'])


if __name__ == '__main__':
    unittest.main()
