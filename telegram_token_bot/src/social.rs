fn title_case(input: &str) -> String {
    input
        .split(|c: char| c == '_' || c == '-' || c.is_whitespace())
        .filter(|segment| !segment.is_empty())
        .map(|segment| {
            let mut chars = segment.chars();
            match chars.next() {
                Some(first) => {
                    let mut result = String::new();
                    result.extend(first.to_uppercase());
                    let rest: String = chars.collect();
                    result.push_str(&rest.to_lowercase());
                    result
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn infer_social_platform(handle: &str) -> String {
    let handle_lower = handle.to_lowercase();

    if handle_lower.contains("twitter.com") || handle_lower.contains("x.com") {
        "Twitter".to_string()
    } else if handle_lower.contains("t.me") {
        "Telegram".to_string()
    } else if handle_lower.contains("discord.gg") || handle_lower.contains("discord.com") {
        "Discord".to_string()
    } else if handle_lower.contains("github.com") {
        "GitHub".to_string()
    } else if handle_lower.contains("facebook.com") {
        "Facebook".to_string()
    } else if handle_lower.contains("instagram.com") {
        "Instagram".to_string()
    } else if handle_lower.contains("linkedin.com") {
        "LinkedIn".to_string()
    } else if handle_lower.contains("reddit.com") {
        "Reddit".to_string()
    } else if handle_lower.contains("youtube.com") {
        "YouTube".to_string()
    } else if handle_lower.contains("twitch.tv") {
        "Twitch".to_string()
    } else if handle_lower.contains("coingecko.com") {
        "CoinGecko".to_string()
    } else if handle_lower.contains("coinmarketcap.com") {
        "CoinMarketCap".to_string()
    } else if handle_lower.contains("bitcointalk.org") {
        "BitcoinTalk".to_string()
    } else if handle_lower.contains("slack.com") {
        "Slack".to_string()
    } else if handle_lower.contains("wechat.com") {
        "WeChat".to_string()
    } else if handle_lower.contains("medium.com") || handle_lower.contains("blog") {
        "Blog".to_string()
    } else if handle_lower.contains("whitepaper") || handle_lower.contains(".pdf") {
        "Whitepaper".to_string()
    } else if handle_lower.contains("mailto:") {
        "Email".to_string()
    } else if handle_lower.starts_with("http") {
        "Website".to_string()
    } else {
        "Social".to_string()
    }
}

pub fn detect_social_platform(url: &str) -> String {
    infer_social_platform(url)
}

pub fn format_social_label(platform: Option<&str>, handle: &str) -> String {
    if let Some(platform) = platform {
        let trimmed = platform.trim();
        if !trimmed.is_empty() {
            return title_case(trimmed);
        }
    }
    infer_social_platform(handle)
}
