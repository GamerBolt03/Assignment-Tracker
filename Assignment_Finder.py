import re


class AssignmentFinder:
    def __init__(self):
        self.positive = {
            'strong': [
                'assignment', 'homework', 'problem set', 'problem_set',
                'lab report', 'lab_report', 'research paper', 'research_paper',
                'term paper', 'term_paper', 'final project', 'final_project',
                'group project', 'group_project', 'thesis', 'dissertation',
                'worksheet', 'workbook', 'essay', 'paper due', 'paper_due',
                'submit your', 'must be submitted', 'assignment due',
                'assignment submission', 'submit assignment',
                'homework help', 'homework due', 'due date',
                'project submission', 'project deadline', 'project due',
                'coursework submission', 'hand in', 'turn in',
                'deliverable', 'milestone', 'capstone',
            ],
            'medium': [
                'deadline', 'due by', 'due on', 'submit', 'complete',
                'grade', 'coursework', 'exercises', 'questions',
                'quiz', 'exam', 'midterm', 'final exam', 'study guide',
                'required reading', 'reading assignment', 'preparation',
                'draft', 'revision', 'resubmit', 'extended deadline',
                'proposal', 'paper', 'report', 'lab', 'problem',
                'exercise', 'essay', 'write', 'coding', 'program',
                'question', 'task', 'score', 'mark', 'result',
            ],
            'weak': [
                'class', 'course', 'lesson', 'study', 'reading',
                'notes', 'syllabus', 'lecture', 'tutorial', 'module',
                'unit', 'chapter', 'week', 'workshop', 'seminar',
            ]
        }

        self.exclusions = [
            'verify your', 'verify email', 'verify account', 'confirm your',
            'confirm email', 'confirm account', 'confirm subscription',
            'welcome to', 'welcome!', 'getting started', 'get started',
            'sign in', 'sign-in', 'log in', 'login', 'logged in',
            'you signed in', 'new sign-in', 'new device', 'unusual sign-in',
            'security alert', 'security code', 'authentication',
            'password reset', 'reset your password', 'change password',
            'recovery', 'account recovery',
            'you\'re invited', 'you are invited', 'invitation',
            'invited to', 'join ', 'has invited you',
            'receipt', 'invoice', 'payment', 'payment received',
            'purchase', 'order confirmation', 'order received',
            'shipping', 'shipped', 'delivered', 'track your',
            'unsubscribe', 'newsletter', 'weekly digest', 'monthly digest',
            ' promotional', 'discount', 'coupon', 'offer',
            'notification', 'do not reply', 'do-not-reply',
            'linkedin', 'facebook', 'twitter', 'instagram', 'youtube',
            'connection request', 'accepted your', 'follow request',
            'microsoft teams', 'slack', 'zoom', 'meeting reminder',
            'calendar', 'event reminder', 'calendar event',
            'your subscription', 'trial', 'upgrade', 'premium',
            'app password', 'authenticator', '2-step', 'two-factor',
            'spam', 'junk', 'bulk', 'advertisement', 'ad -',
        ]

    def is_assignment(self, subject, body):
        text = f"{subject} {body}".lower()
        subject_lower = subject.lower()

        score = 0

        for kw in self.positive['strong']:
            score += len(re.findall(re.escape(kw), text)) * 4

        for kw in self.positive['medium']:
            score += len(re.findall(re.escape(kw), text)) * 2

        for kw in self.positive['weak']:
            score += len(re.findall(re.escape(kw), text)) * 1

        for kw in self.positive['strong'] + self.positive['medium']:
            if kw in subject_lower:
                score += 3

        for ex in self.exclusions:
            if ex in text:
                score -= 5

        course_pattern = re.search(r'\b[a-z]+\s*\d{3,4}\b', subject_lower)
        if course_pattern:
            score += 3

        if 'reminder' in subject_lower and any(kw in subject_lower for kw in
            ['due', 'deadline', 'submit', 'assignment', 'project', 'homework', 'proposal']):
            score += 2

        score = max(score, 0)
        return score >= 6
