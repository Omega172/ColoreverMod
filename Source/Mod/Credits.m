#import <UIKit/UIKit.h>

@interface clOmegaCredits : NSObject
{
    UIVisualEffectView *m_pCard;
    BOOL m_bScheduled;
    BOOL m_bShown;
}
- (void)schedule;
- (void)onReady:(NSNotification *)pstNotification;
- (void)show;
- (void)dismiss;
- (void)openGitHub;
@end

@implementation clOmegaCredits

- (void)onReady:(NSNotification *)pstNotification
{
    [self schedule];
}

- (void)schedule
{
    if (m_bScheduled || m_bShown)
        return;
    m_bScheduled = YES;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        self->m_bScheduled = NO;
        [self show];
    });
}

- (UIWindow *)activeWindow
{
    UIApplication *pApplication = [UIApplication sharedApplication];
    for (UIScene *pScene in pApplication.connectedScenes)
    {
        if (pScene.activationState != UISceneActivationStateForegroundActive || ![pScene isKindOfClass:[UIWindowScene class]])
            continue;
        for (UIWindow *pWindow in ((UIWindowScene *)pScene).windows)
        {
            if (pWindow.isKeyWindow && !pWindow.hidden && pWindow.windowLevel == UIWindowLevelNormal)
                return pWindow;
        }
    }
    id<UIApplicationDelegate> pDelegate = pApplication.delegate;
    if ([pDelegate respondsToSelector:@selector(window)])
    {
        UIWindow *pWindow = pDelegate.window;
        if (pWindow.isKeyWindow && !pWindow.hidden && pWindow.windowLevel == UIWindowLevelNormal)
            return pWindow;
    }
    return nil;
}

- (void)show
{
    if (m_bShown || [UIApplication sharedApplication].applicationState != UIApplicationStateActive)
        return;
    UIWindow *pWindow = [self activeWindow];
    if (!pWindow.rootViewController || !pWindow.rootViewController.view.window)
        return;
    UIImage *pLogo = [UIImage imageWithContentsOfFile:[[NSBundle mainBundle] pathForResource:@"Omega172" ofType:@"png"]];
    if (!pLogo)
        return;
    m_pCard = [[UIVisualEffectView alloc] initWithEffect:[UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemMaterial]];
    m_pCard.translatesAutoresizingMaskIntoConstraints = NO;
    m_pCard.layer.cornerRadius = 18;
    m_pCard.clipsToBounds = YES;
    m_pCard.accessibilityIdentifier = @"Omega172.ModCredits";
    UIImageView *pImage = [[UIImageView alloc] initWithImage:pLogo];
    pImage.contentMode = UIViewContentModeScaleAspectFit;
    pImage.isAccessibilityElement = YES;
    pImage.accessibilityLabel = @"Omega172 logo";
    [pImage.widthAnchor constraintEqualToConstant:48].active = YES;
    [pImage.heightAnchor constraintEqualToConstant:48].active = YES;
    UILabel *pTitle = [[UILabel alloc] init];
    pTitle.text = @"Mod by Omega172";
    pTitle.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
    pTitle.adjustsFontForContentSizeCategory = YES;
    pTitle.textColor = [UIColor labelColor];
    pTitle.numberOfLines = 0;
    UIButton *pGitHub = [UIButton buttonWithType:UIButtonTypeSystem];
    [pGitHub setTitle:@"View GitHub" forState:UIControlStateNormal];
    pGitHub.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
    pGitHub.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    pGitHub.titleLabel.adjustsFontForContentSizeCategory = YES;
    pGitHub.accessibilityHint = @"Opens github.com/Omega172";
    [pGitHub.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    [pGitHub addTarget:self action:@selector(openGitHub) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *pText = [[UIStackView alloc] initWithArrangedSubviews:@[pTitle, pGitHub]];
    pText.axis = UILayoutConstraintAxisVertical;
    pText.spacing = 0;
    UIButton *pDismiss = [UIButton buttonWithType:UIButtonTypeSystem];
    [pDismiss setTitle:@"Dismiss" forState:UIControlStateNormal];
    pDismiss.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    [pDismiss.widthAnchor constraintEqualToConstant:64].active = YES;
    [pDismiss.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    [pDismiss addTarget:self action:@selector(dismiss) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *pRow = [[UIStackView alloc] initWithArrangedSubviews:@[pImage, pText, pDismiss]];
    pRow.translatesAutoresizingMaskIntoConstraints = NO;
    pRow.axis = UILayoutConstraintAxisHorizontal;
    pRow.alignment = UIStackViewAlignmentCenter;
    pRow.spacing = 12;
    [m_pCard.contentView addSubview:pRow];
    [pWindow addSubview:m_pCard];
    NSLayoutConstraint *pWidth = [m_pCard.widthAnchor constraintEqualToAnchor:pWindow.widthAnchor constant:-32];
    pWidth.priority = UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [m_pCard.centerXAnchor constraintEqualToAnchor:pWindow.centerXAnchor],
        [m_pCard.topAnchor constraintEqualToAnchor:pWindow.safeAreaLayoutGuide.topAnchor constant:12],
        [m_pCard.widthAnchor constraintLessThanOrEqualToConstant:380],
        pWidth,
        [pRow.leadingAnchor constraintEqualToAnchor:m_pCard.contentView.leadingAnchor constant:12],
        [pRow.trailingAnchor constraintEqualToAnchor:m_pCard.contentView.trailingAnchor constant:-12],
        [pRow.topAnchor constraintEqualToAnchor:m_pCard.contentView.topAnchor constant:10],
        [pRow.bottomAnchor constraintEqualToAnchor:m_pCard.contentView.bottomAnchor constant:-10]
    ]];
    m_bShown = YES;
    m_pCard.alpha = 0;
    [UIView animateWithDuration:0.2 animations:^{ self->m_pCard.alpha = 1; }];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self dismiss]; });
}

- (void)dismiss
{
    UIVisualEffectView *pCard = m_pCard;
    m_pCard = nil;
    [UIView animateWithDuration:0.2 animations:^{ pCard.alpha = 0; } completion:^(BOOL bFinished) { [pCard removeFromSuperview]; }];
}

- (void)openGitHub
{
    [self dismiss];
    [[UIApplication sharedApplication] openURL:[NSURL URLWithString:@"https://github.com/Omega172"] options:@{} completionHandler:nil];
}

@end

__attribute__((constructor)) static void InitializeCredits(void)
{
    dispatch_async(dispatch_get_main_queue(), ^{
        static clOmegaCredits *s_pCredits;
        s_pCredits = [[clOmegaCredits alloc] init];
        NSNotificationCenter *pNotifications = [NSNotificationCenter defaultCenter];
        [pNotifications addObserver:s_pCredits selector:@selector(onReady:) name:UIApplicationDidBecomeActiveNotification object:nil];
        [pNotifications addObserver:s_pCredits selector:@selector(onReady:) name:UIWindowDidBecomeKeyNotification object:nil];
        [s_pCredits schedule];
    });
}
